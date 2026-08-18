import uuid
from datetime import timedelta

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import IntegrityError, OperationalError, transaction
from django.utils import timezone

from apps.events.models import Event

from .constants import HOLD_DURATION_MINUTES, MAX_SEATS_PER_HOLD
from .models import EventSeat, SeatHold
from .serializers import serialize_seats_for_ws


class NotSeatedEventError(Exception):
    """Raised when a seating operation is attempted against a non-assigned-seating event."""


class AlreadyInstantiatedError(Exception):
    """Raised when POST .../seats/instantiate/ is called a second time for the same event."""


class UncoveredSectionsError(Exception):
    """Raised when instantiate is attempted before every venue section has a tier mapping."""

    def __init__(self, sections: list[str]):
        self.sections = sections
        super().__init__(
            "These venue sections have no ticket-tier mapping: " + ", ".join(sections)
        )


class EventNotHoldableError(Exception):
    """Raised when a hold is requested against an event that isn't currently approved."""


class EmptySeatSelectionError(Exception):
    """Raised when seat_ids is empty."""


class TooManySeatsError(Exception):
    """Raised when a single hold request asks for more than MAX_SEATS_PER_HOLD seats."""

    def __init__(self, requested: int):
        self.requested = requested
        super().__init__(
            f"A single hold request can cover at most {MAX_SEATS_PER_HOLD} seats "
            f"(requested {requested})."
        )


class SeatsNotFoundError(Exception):
    """Raised when one or more seat_ids don't belong to this event's instantiated seats."""

    def __init__(self, seat_ids: list):
        self.seat_ids = seat_ids
        super().__init__(
            "Unknown seat ids for this event: " + ", ".join(str(s) for s in seat_ids)
        )


class SeatsUnavailableError(Exception):
    """Raised when one or more requested seats are held/booked by someone else."""

    def __init__(self, seat_ids: list):
        self.seat_ids = seat_ids
        super().__init__(
            "Seats already held or booked: " + ", ".join(str(s) for s in seat_ids)
        )


class SeatLockConflictError(Exception):
    """Raised when NOWAIT fails to acquire a lock on one or more requested seats."""


def instantiate_event_seats(event: Event) -> list[EventSeat]:
    if not event.is_seated:
        raise NotSeatedEventError("This event does not use assigned seating.")
    if event.venue_id is None:
        raise NotSeatedEventError("This event has no venue to instantiate seats from.")
    if EventSeat.objects.filter(event=event).exists():
        raise AlreadyInstantiatedError(
            "Seats have already been instantiated for this event."
        )

    venue_sections = set(event.venue.seats.values_list("section", flat=True).distinct())
    tier_by_section = dict(
        event.tier_section_mappings.values_list("section", "ticket_tier_id")
    )
    uncovered = sorted(venue_sections - set(tier_by_section))
    if uncovered:
        raise UncoveredSectionsError(uncovered)

    seats_to_create = [
        EventSeat(
            event=event,
            seat=seat,
            ticket_tier_id=tier_by_section[seat.section],
        )
        for seat in event.venue.seats.all()
    ]

    try:
        with transaction.atomic():
            return EventSeat.objects.bulk_create(seats_to_create)
    except IntegrityError as exc:
        raise AlreadyInstantiatedError(
            "Seats have already been instantiated for this event."
        ) from exc


def hold_seats(
    *, event: Event, seat_ids: list, user
) -> tuple[uuid.UUID, "timezone.datetime", list]:
    seat_ids = list(dict.fromkeys(seat_ids))

    if not seat_ids:
        raise EmptySeatSelectionError("seat_ids must not be empty.")
    if len(seat_ids) > MAX_SEATS_PER_HOLD:
        raise TooManySeatsError(len(seat_ids))
    if not event.is_seated:
        raise NotSeatedEventError("This event does not use assigned seating.")
    if event.status != Event.Status.APPROVED:
        raise EventNotHoldableError(
            "Seats can only be held against an approved, currently-running event."
        )

    group_id = uuid.uuid4()
    expires_at = timezone.now() + timedelta(minutes=HOLD_DURATION_MINUTES)

    try:
        with transaction.atomic():
            locked_seats = list(
                EventSeat.objects.select_for_update(nowait=True, of=("self",))
                .select_related("seat", "ticket_tier")
                .filter(event=event, id__in=seat_ids)
            )
            found_ids = {seat.id for seat in locked_seats}
            missing_ids = [sid for sid in seat_ids if sid not in found_ids]
            if missing_ids:
                raise SeatsNotFoundError(missing_ids)

            now = timezone.now()
            existing_holds = {
                hold.event_seat_id: hold
                for hold in SeatHold.objects.filter(event_seat__in=locked_seats)
            }

            conflict_ids = []
            for seat in locked_seats:
                if seat.status == EventSeat.Status.AVAILABLE:
                    continue
                if seat.status == EventSeat.Status.BOOKED:
                    conflict_ids.append(seat.id)
                    continue
                hold = existing_holds.get(seat.id)
                if hold is not None and hold.user_id == user.id:
                    continue
                if hold is not None and hold.expires_at < now:
                    continue
                conflict_ids.append(seat.id)
            if conflict_ids:
                raise SeatsUnavailableError(conflict_ids)

            SeatHold.objects.filter(event_seat__in=locked_seats).delete()
            EventSeat.objects.filter(id__in=found_ids).update(
                status=EventSeat.Status.HELD
            )
            SeatHold.objects.bulk_create(
                SeatHold(
                    group_id=group_id,
                    event_seat=seat,
                    user=user,
                    expires_at=expires_at,
                )
                for seat in locked_seats
            )

            for seat in locked_seats:
                seat.status = EventSeat.Status.HELD

            transaction.on_commit(
                lambda: _broadcast_seat_update(event=event, seats=locked_seats)
            )
    except OperationalError as exc:
        raise SeatLockConflictError(
            "One or more of these seats are being processed by another request right now. "
            "Please try again."
        ) from exc

    return group_id, expires_at, locked_seats


def _broadcast_seat_update(*, event: Event, seats: list[EventSeat]) -> None:
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        f"seats_{event.slug}",
        {
            "type": "seat_update",
            "seats": serialize_seats_for_ws(seats),
        },
    )
