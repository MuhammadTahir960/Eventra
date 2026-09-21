import logging

import stripe
from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.bookings.models import Booking
from apps.seating.models import EventSeat
from apps.seating.services import broadcast_seat_update
from apps.tickets.models import Ticket
from apps.tickets.tasks import generate_ticket_pdf

from .models import Payment

stripe.api_key = settings.STRIPE_SECRET_KEY

CURRENCY = "usd"

logger = logging.getLogger(__name__)


class PaymentGatewayError(Exception):
    """stripe.PaymentIntent.create() raised stripe.error.StripeError."""


class WebhookSignatureError(Exception):
    """Raised when a webhook payload's signature can't be verified."""


class PaymentNotFoundError(Exception):
    """Raised when a webhook references a payment_intent_id with no matching Payment row."""


def _to_cents(total_amount):
    return int(round(total_amount * 100))


def create_or_refresh_payment_intent(booking):
    payment = Payment.objects.filter(booking=booking).first()
    if payment is not None and payment.stripe_payment_intent_id:
        return payment

    amount_cents = _to_cents(booking.total_amount)

    try:
        intent = stripe.PaymentIntent.create(
            amount=amount_cents,
            currency=CURRENCY,
            metadata={"booking_id": str(booking.id)},
            idempotency_key=booking.idempotency_key,
        )
    except stripe.error.StripeError as exc:
        raise PaymentGatewayError(
            "Unable to reach the payment provider. Please try again."
        ) from exc

    with transaction.atomic():
        payment = Payment.objects.select_for_update().filter(booking=booking).first()

        if payment is not None and payment.stripe_payment_intent_id:
            return payment

        if payment is None:
            try:
                with transaction.atomic():
                    payment = Payment.objects.create(
                        booking=booking,
                        stripe_payment_intent_id=intent.id,
                        client_secret=intent.client_secret,
                        amount=amount_cents,
                        currency=CURRENCY,
                        status=Payment.Status.PENDING,
                    )
            except IntegrityError:
                payment = Payment.objects.get(booking=booking)
        else:
            payment.stripe_payment_intent_id = intent.id
            payment.client_secret = intent.client_secret
            payment.amount = amount_cents
            payment.save(
                update_fields=[
                    "stripe_payment_intent_id",
                    "client_secret",
                    "amount",
                    "updated_at",
                ]
            )

    return payment


def verify_stripe_webhook_signature(payload: bytes, sig_header: str):
    try:
        return stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except (ValueError, stripe.error.SignatureVerificationError) as exc:
        raise WebhookSignatureError("Invalid webhook signature or payload") from exc


_UNFULFILLABLE_EVENT_STATUSES = ("cancelled", "completed", "rejected")


def confirm_payment_from_webhook(payment_intent_id: str) -> Booking:
    payment = Payment.objects.filter(stripe_payment_intent_id=payment_intent_id).first()
    if payment is None:
        raise PaymentNotFoundError(
            f"No Payment row for PaymentIntent {payment_intent_id}"
        )
    if payment.status == Payment.Status.REFUNDED:
        return Booking.objects.get(id=payment.booking_id)

    with transaction.atomic():
        booking = Booking.objects.select_for_update().get(id=payment.booking_id)

        if booking.status == Booking.Status.CONFIRMED:
            return booking

        seats = list(
            EventSeat.objects.select_for_update(of=("self",))
            .filter(held_booking=booking)
            .select_related("event", "seat", "ticket_tier")
        )

        fulfillable = (
            booking.status == Booking.Status.PENDING
            and bool(seats)
            and all(s.event.status not in _UNFULFILLABLE_EVENT_STATUSES for s in seats)
        )

        if not fulfillable:
            payment.status = Payment.Status.SUCCEEDED
            payment.save(update_fields=["status", "updated_at"])
            for seat in seats:
                seat.held_booking = None
            EventSeat.objects.bulk_update(seats, ["held_booking"])
        else:
            booking.status = Booking.Status.CONFIRMED
            booking.save(update_fields=["status", "updated_at"])

            for seat in seats:
                seat.status = EventSeat.Status.BOOKED
                seat.held_booking = None
                seat.save(update_fields=["status", "held_booking"])

            Ticket.objects.bulk_create(
                [Ticket(booking=booking, event_seat=seat) for seat in seats]
            )

            payment.status = Payment.Status.SUCCEEDED
            payment.save(update_fields=["status", "updated_at"])

            event = seats[0].event
            transaction.on_commit(
                lambda: broadcast_seat_update(event=event, seats=seats), robust=True
            )
            transaction.on_commit(
                lambda: generate_ticket_pdf.delay(str(booking.id)), robust=True
            )
            transaction.on_commit(
                lambda: _enqueue_confirmation_email(str(booking.id)), robust=True
            )

    if not fulfillable:
        refund_booking(booking)
        try:
            from apps.notifications.tasks import send_refund_email

            send_refund_email.delay(str(booking.id), False)
        except Exception:
            logger.exception("Refund notice enqueue failed for booking %s", booking.id)
        booking.refresh_from_db()

    return booking


def mark_payment_from_webhook(payment_intent_id: str, new_status: str) -> None:
    Payment.objects.filter(
        stripe_payment_intent_id=payment_intent_id, status=Payment.Status.PENDING
    ).update(status=new_status, updated_at=timezone.now())


def cancel_payment_intent_if_unpaid(booking: Booking) -> bool:
    payment = Payment.objects.filter(booking=booking).first()
    if payment is None or not payment.stripe_payment_intent_id:
        return True

    try:
        stripe.PaymentIntent.cancel(payment.stripe_payment_intent_id)
    except stripe.error.InvalidRequestError:
        try:
            intent = stripe.PaymentIntent.retrieve(payment.stripe_payment_intent_id)
        except stripe.error.StripeError:
            return False
        if intent.status != "canceled":
            return False
    except stripe.error.StripeError:
        logger.exception("Could not cancel PaymentIntent for booking %s", booking.id)
        return False

    Payment.objects.filter(id=payment.id).exclude(
        status=Payment.Status.SUCCEEDED
    ).update(status=Payment.Status.CANCELED, updated_at=timezone.now())
    return True


def _enqueue_confirmation_email(booking_id: str) -> None:
    from apps.notifications.tasks import send_confirmation_email

    send_confirmation_email.delay(booking_id)


def refund_booking(booking: Booking) -> None:
    payment = Payment.objects.get(booking=booking)

    if payment.status == Payment.Status.REFUNDED:
        return

    try:
        stripe.Refund.create(
            payment_intent=payment.stripe_payment_intent_id,
            idempotency_key=f"refund-{payment.id}",
        )
    except stripe.error.StripeError as exc:
        raise PaymentGatewayError(str(exc)) from exc

    with transaction.atomic():
        payment = Payment.objects.select_for_update().get(id=payment.id)
        if payment.status == Payment.Status.REFUNDED:
            return

        payment.status = Payment.Status.REFUNDED
        payment.save(update_fields=["status", "updated_at"])

        booking.tickets.update(
            status=Ticket.Status.CANCELLED, updated_at=timezone.now()
        )

        booking.status = Booking.Status.REFUNDED
        booking.save(update_fields=["status", "updated_at"])


def refund_event_bookings(event_id, *, only_failed: bool = False) -> None:
    statuses = (
        [Booking.Status.REFUND_FAILED, Booking.Status.CONFIRMED]
        if only_failed
        else [Booking.Status.CONFIRMED]
    )
    bookings = Booking.objects.filter(
        tickets__event_seat__event_id=event_id, status__in=statuses
    ).distinct()

    for booking in bookings:
        try:
            refund_booking(booking)
        except Exception:
            logger.exception(
                "Refund failed for booking %s (event %s)", booking.id, event_id
            )
            Booking.objects.filter(id=booking.id).update(
                status=Booking.Status.REFUND_FAILED, updated_at=timezone.now()
            )
            continue

        try:
            from apps.notifications.tasks import send_refund_email

            send_refund_email.delay(str(booking.id))
        except Exception:
            logger.exception(
                "Refund succeeded but confirmation email failed for booking %s",
                booking.id,
            )
