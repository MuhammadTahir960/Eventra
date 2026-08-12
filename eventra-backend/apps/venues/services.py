from django.db import IntegrityError, transaction
from apps.seating.models import EventSeat
from .models import Venue, Seat


class DuplicateSeatError(Exception):
    """Raised when a bulk seat-template payload collides with existing seats for this venue."""


class SeatTemplateExistsError(Exception):
    """Raised when a venue already has a seat template and the caller isn't allowed to modify it."""


class CapacityExceededError(Exception):
    """Raised when a payload would put the venue's seat count over its declared capacity."""


class SeatTemplateInUseError(Exception):
    """
    Raised when a reseed (?hard reseed via allow_reseed=True) is attempted, but one or more of
    the venue's existing seats already has event_seats instantiated against it.
    """


@transaction.atomic
def bulk_create_seat_template(
    venue: Venue, sections: list[dict], *, allow_reseed: bool = False
) -> list[Seat]:

    venue = Venue.all_objects.select_for_update().get(pk=venue.pk)

    existing_seat_count = venue.seats.count()

    if existing_seat_count > 0 and not allow_reseed:
        raise SeatTemplateExistsError(
            "This venue already has a seat template. Contact an admin to modify it."
        )

    if existing_seat_count > 0 and EventSeat.objects.filter(seat__venue=venue).exists():
        raise SeatTemplateInUseError(
            "This venue's seats are already instantiated for one or more events — the "
            "template can't be replaced while that event history exists."
        )

    new_seat_count = sum(
        row["seat_count"] for section in sections for row in section["rows"]
    )

    if new_seat_count > venue.capacity:
        raise CapacityExceededError(
            f"This would create {new_seat_count} seats, "
            f"over the venue's declared capacity of {venue.capacity}."
        )

    if existing_seat_count > 0:
        venue.seats.all().delete()

    seat_objects = [
        Seat(
            venue=venue,
            section=section["name"],
            row_label=row["row_label"],
            seat_number=seat_number,
        )
        for section in sections
        for row in section["rows"]
        for seat_number in range(1, row["seat_count"] + 1)
    ]

    try:
        return Seat.objects.bulk_create(seat_objects)
    except IntegrityError as exc:
        raise DuplicateSeatError(
            "One or more seats in this template already exist for this venue."
        ) from exc
