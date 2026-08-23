import uuid
from decimal import Decimal

import stripe
from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.payments.models import Payment
from apps.seating.models import EventSeat, SeatHold
from apps.seating.serializers import serialize_seats_for_ws

from .models import Booking

stripe.api_key = settings.STRIPE_SECRET_KEY


class HoldNotFoundError(Exception):
    """No SeatHold rows match the given hold_id for the requesting user."""


class HoldExpiredError(Exception):
    """The hold group exists but has already expired."""


class BookingNotPendingError(Exception):
    """The booking exists but isn't in a state the requested action allows."""


class PaymentGatewayError(Exception):
    """stripe.PaymentIntent.create() raised stripe.error.StripeError."""


def _compute_total_amount(seat_holds):
    total = Decimal("0.00")
    for hold in seat_holds:
        seat = hold.event_seat
        price = (
            seat.price_override
            if seat.price_override is not None
            else seat.ticket_tier.price
        )
        total += price
    return total


def create_booking_from_hold(hold_id, user):
    existing = Booking.objects.filter(source_hold_group_id=hold_id, user=user).first()
    if existing is not None:
        return existing, False

    with transaction.atomic():
        seat_holds = list(
            SeatHold.objects.select_for_update(of=("self",))
            .filter(group_id=hold_id, user=user)
            .select_related(
                "event_seat",
                "event_seat__ticket_tier",
                "event_seat__event",
            )
        )

        if not seat_holds:
            existing = Booking.objects.filter(
                source_hold_group_id=hold_id, user=user
            ).first()
            if existing is not None:
                return existing, False
            raise HoldNotFoundError(
                f"No active hold found for hold_id={hold_id} and this user."
            )

        now = timezone.now()
        if any(hold.expires_at < now for hold in seat_holds):
            raise HoldExpiredError(f"Hold {hold_id} has already expired.")

        total_amount = _compute_total_amount(seat_holds)
        event_seat_ids = [hold.event_seat_id for hold in seat_holds]

        SeatHold.objects.filter(group_id=hold_id, user=user).delete()

        try:
            with transaction.atomic():
                booking = Booking.objects.create(
                    user=user,
                    status=Booking.Status.PENDING,
                    total_amount=total_amount,
                    source_hold_group_id=hold_id,
                    idempotency_key=str(uuid.uuid4()),
                )
            created = True
        except IntegrityError:
            booking = Booking.objects.get(source_hold_group_id=hold_id, user=user)
            created = False

        EventSeat.objects.filter(id__in=event_seat_ids).update(held_booking=booking)

    return booking, created


def checkout_booking(booking):
    if booking.status != Booking.Status.PENDING:
        raise BookingNotPendingError(
            f"Booking {booking.id} is '{booking.status}', not 'pending'."
        )

    payment = Payment.objects.filter(booking=booking).first()
    if payment is not None and payment.stripe_payment_intent_id:
        return payment

    amount_cents = int(round(booking.total_amount * 100))

    try:
        intent = stripe.PaymentIntent.create(
            amount=amount_cents,
            currency="usd",
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
                        currency="usd",
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


def _broadcast_seats_released(event_slug, event_seats):
    from asgiref.sync import async_to_sync
    from channels.layers import get_channel_layer

    channel_layer = get_channel_layer()
    if channel_layer is None:
        return

    async_to_sync(channel_layer.group_send)(
        f"seats_{event_slug}",
        {
            "type": "seat_update",
            "seats": serialize_seats_for_ws(event_seats),
        },
    )


def cancel_booking(booking):
    if booking.status != Booking.Status.PENDING:
        raise BookingNotPendingError(
            f"Booking {booking.id} is '{booking.status}', not 'pending'."
        )

    with transaction.atomic():
        seats = list(
            EventSeat.objects.select_for_update(of=("self",))
            .filter(held_booking=booking)
            .select_related("event")
        )

        EventSeat.objects.filter(held_booking=booking).update(
            status=EventSeat.Status.AVAILABLE,
            held_booking=None,
        )

        booking.status = Booking.Status.CANCELLED
        booking.save(update_fields=["status", "updated_at"])

        for seat in seats:
            seat.status = EventSeat.Status.AVAILABLE
            seat.held_booking = None

        seats_by_event_slug = {}
        for seat in seats:
            seats_by_event_slug.setdefault(seat.event.slug, []).append(seat)

        for slug, event_seats in seats_by_event_slug.items():
            transaction.on_commit(
                lambda slug=slug, event_seats=event_seats: _broadcast_seats_released(
                    slug, event_seats
                )
            )

    return booking
