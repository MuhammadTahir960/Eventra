from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.events.models import Event
from apps.payments.services import (
    cancel_payment_intent_if_unpaid,
    create_or_refresh_payment_intent,
    fulfil_booking,
)
from apps.seating.models import EventSeat, SeatHold
from apps.seating.services import notify_seats_available
from apps.tickets.models import Ticket

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

        seats = [hold.event_seat for hold in seat_holds]

        SeatHold.objects.filter(group_id=hold_id, user=user).delete()

        try:
            with transaction.atomic():
                booking = Booking.objects.create(
                    user=user,
                    status=Booking.Status.PENDING,
                    source_hold_group_id=hold_id,
                )
                Ticket.objects.bulk_create(
                    Ticket(booking=booking, event_seat=seat, price=seat.price)
                    for seat in seats
                )
            created = True
        except IntegrityError:
            booking = Booking.objects.get(source_hold_group_id=hold_id, user=user)
            created = False

    return booking, created


def checkout_booking(booking):
    if booking.status != Booking.Status.PENDING:
        raise BookingNotPendingError(
            f"Booking {booking.id} is '{booking.status}', not 'pending'."
        )

    if booking.created_at < timezone.now() - timedelta(minutes=BOOKING_EXPIRY_MINUTES):
        raise BookingExpiredError(f"Booking {booking.id} has expired.")

    seat = booking.held_seats().select_related("event").first()
    if seat is not None:
        _ensure_event_sellable(seat.event)

    if booking.total_amount == 0:
        _confirm_free_booking(booking)
        return None
    return create_or_refresh_payment_intent(booking)


def _confirm_free_booking(booking) -> None:
    with transaction.atomic():
        booking = Booking.objects.select_for_update().get(id=booking.id)
        seats = list(
            booking.held_seats()
            .select_for_update(of=("self",))
            .select_related("event", "seat", "ticket_tier")
        )
        if booking.status != Booking.Status.PENDING:
            raise BookingNotPendingError(
                f"Booking {booking.id} is '{booking.status}', not 'pending'."
            )
        if not seats:
            raise BookingExpiredError(f"Booking {booking.id} has expired.")
        _ensure_event_sellable(
            Event.all_objects.select_for_update().get(pk=seats[0].event_id)
        )
        fulfil_booking(booking, seats)


def sweep_expired_pending_bookings() -> None:
    cutoff = timezone.now() - timedelta(minutes=BOOKING_EXPIRY_MINUTES)
    _release_unpaid_bookings(created_at__lt=cutoff)


def release_pending_bookings_for_event(*, user, event) -> None:
    _release_unpaid_bookings(user=user, tickets__event_seat__event=event)


def cancel_pending_bookings_for_event(event_id) -> None:
    _release_unpaid_bookings(tickets__event_seat__event_id=event_id)


def _release_unpaid_bookings(**filters) -> None:
    booking_ids = list(
        Booking.objects.filter(status=Booking.Status.PENDING, **filters)
        .values_list("id", flat=True)
        .distinct()
    )
    for booking_id in booking_ids:
        booking = Booking.objects.filter(id=booking_id).first()
        if booking is None or not cancel_payment_intent_if_unpaid(booking):
            continue
        _release_booking(booking_id)


def _release_booking(booking_id) -> None:
    with transaction.atomic():
        booking = Booking.objects.select_for_update().filter(id=booking_id).first()
        if booking is None or booking.status != Booking.Status.PENDING:
            return

        seats = list(
            booking.held_seats().select_for_update(of=("self",)).select_related("event")
        )
        for seat in seats:
            seat.status = EventSeat.Status.AVAILABLE
        EventSeat.objects.bulk_update(seats, ["status"])

        booking.status = Booking.Status.CANCELLED
        booking.save(update_fields=["status", "updated_at"])
        booking.tickets.filter(status=Ticket.Status.PENDING).update(
            status=Ticket.Status.CANCELLED, updated_at=timezone.now()
        )
        notify_seats_available(seats)
