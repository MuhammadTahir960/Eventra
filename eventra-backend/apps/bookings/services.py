import uuid
from datetime import timedelta
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.events.models import Event
from apps.payments.services import (
    cancel_payment_intent_if_unpaid,
    create_or_refresh_payment_intent,
)
from apps.seating.models import EventSeat, SeatHold
from apps.seating.services import notify_internal_broadcast

from .models import Booking

BOOKING_EXPIRY_MINUTES = 5


class HoldNotFoundError(Exception):
    """No SeatHold rows match the given hold_id for the requesting user."""


class HoldExpiredError(Exception):
    """The hold group exists but has already expired."""


class BookingNotPendingError(Exception):
    """The booking exists but isn't in a state the requested action allows."""


class BookingExpiredError(Exception):
    """The unpaid booking is past its payment window and is about to be swept."""


class EventClosedError(Exception):
    """The event is no longer approved/running, so it can't be sold."""


def _ensure_event_sellable(event) -> None:
    if event.status != Event.Status.APPROVED or event.end_datetime <= timezone.now():
        raise EventClosedError("This event is no longer available for booking.")


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
        held_seat_ids = list(
            SeatHold.objects.filter(group_id=hold_id, user=user).values_list(
                "event_seat_id", flat=True
            )
        )
        list(
            EventSeat.objects.select_for_update(of=("self",))
            .filter(id__in=held_seat_ids)
            .order_by("id")
        )

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

        _ensure_event_sellable(seat_holds[0].event_seat.event)

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

    if booking.created_at < timezone.now() - timedelta(minutes=BOOKING_EXPIRY_MINUTES):
        raise BookingExpiredError(f"Booking {booking.id} has expired.")

    seat = (
        EventSeat.objects.filter(held_booking=booking).select_related("event").first()
    )
    if seat is not None:
        _ensure_event_sellable(seat.event)

    return create_or_refresh_payment_intent(booking)


def sweep_expired_pending_bookings() -> None:
    cutoff = timezone.now() - timedelta(minutes=BOOKING_EXPIRY_MINUTES)
    stale_booking_ids = list(
        Booking.objects.filter(
            status=Booking.Status.PENDING, created_at__lt=cutoff
        ).values_list("id", flat=True)
    )

    for booking_id in stale_booking_ids:
        booking = Booking.objects.filter(id=booking_id).first()
        if booking is None or not cancel_payment_intent_if_unpaid(booking):
            continue
        _release_one_expired_booking(booking_id)


def _release_one_expired_booking(booking_id) -> None:
    with transaction.atomic():
        booking = Booking.objects.select_for_update().filter(id=booking_id).first()
        if booking is None or booking.status != Booking.Status.PENDING:
            return

        seats = list(
            EventSeat.objects.select_for_update(of=("self",))
            .filter(held_booking=booking)
            .select_related("event")
        )
        for seat in seats:
            seat.status = EventSeat.Status.AVAILABLE
            seat.held_booking = None
        EventSeat.objects.bulk_update(seats, ["status", "held_booking"])

        booking.status = Booking.Status.CANCELLED
        booking.save(update_fields=["status", "updated_at"])

        seat_ids_by_event_slug: dict[str, list] = {}
        for seat in seats:
            seat_ids_by_event_slug.setdefault(seat.event.slug, []).append(seat.id)

        for event_slug, seat_ids in seat_ids_by_event_slug.items():
            transaction.on_commit(
                lambda event_slug=event_slug, seat_ids=seat_ids: notify_internal_broadcast(
                    event_slug=event_slug, seat_ids=seat_ids, status_label="available"
                ),
                robust=True,
            )


def cancel_pending_bookings_for_event(event_id) -> None:
    booking_ids = list(
        Booking.objects.filter(
            status=Booking.Status.PENDING, held_event_seats__event_id=event_id
        )
        .values_list("id", flat=True)
        .distinct()
    )
    for booking_id in booking_ids:
        booking = Booking.objects.filter(id=booking_id).first()
        if booking is None or not cancel_payment_intent_if_unpaid(booking):
            continue
        with transaction.atomic():
            locked = Booking.objects.select_for_update().get(id=booking_id)
            if locked.status != Booking.Status.PENDING:
                continue
            seats = list(
                EventSeat.objects.select_for_update(of=("self",))
                .filter(held_booking=locked)
                .select_related("event")
            )
            for seat in seats:
                seat.status = EventSeat.Status.AVAILABLE
                seat.held_booking = None
            EventSeat.objects.bulk_update(seats, ["status", "held_booking"])
            locked.status = Booking.Status.CANCELLED
            locked.save(update_fields=["status", "updated_at"])

            seat_ids_by_event_slug: dict[str, list] = {}
            for seat in seats:
                seat_ids_by_event_slug.setdefault(seat.event.slug, []).append(seat.id)
            for event_slug, seat_ids in seat_ids_by_event_slug.items():
                transaction.on_commit(
                    lambda event_slug=event_slug, seat_ids=seat_ids: notify_internal_broadcast(
                        event_slug=event_slug,
                        seat_ids=seat_ids,
                        status_label="available",
                    ),
                    robust=True,
                )
