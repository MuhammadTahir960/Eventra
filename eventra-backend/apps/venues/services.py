from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.seating.models import EventSeat

from .models import Seat, Venue, VenueRequest


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


class VenueRequestNotPendingError(Exception):
    """Raised when reject/fulfil is attempted on a request no longer pending."""


class VenueRequestAdminNotesRequiredError(Exception):
    """Raised when POST /venues/requests/{id}/reject/ is called with no (or blank) admin_notes."""


MAX_ADMIN_NOTES_LENGTH = 2000


def reject_venue_request(venue_request: VenueRequest, admin_notes: str) -> VenueRequest:
    with transaction.atomic():
        return _reject_locked(venue_request, admin_notes)


def _reject_locked(venue_request: VenueRequest, admin_notes: str) -> VenueRequest:
    venue_request.refresh_from_db(
        from_queryset=VenueRequest.objects.select_for_update()
    )
    if venue_request.status != VenueRequest.Status.PENDING:
        raise VenueRequestNotPendingError(
            "Only pending venue requests can be rejected "
            f"(current status: {venue_request.get_status_display()})."
        )
    admin_notes = (admin_notes or "").strip()
    if not admin_notes:
        raise VenueRequestAdminNotesRequiredError(
            "A non-empty 'admin_notes' is required to reject a venue request."
        )
    if len(admin_notes) > MAX_ADMIN_NOTES_LENGTH:
        raise VenueRequestAdminNotesRequiredError(
            f"'admin_notes' must be at most {MAX_ADMIN_NOTES_LENGTH} characters."
        )
    venue_request.status = VenueRequest.Status.REJECTED
    venue_request.admin_notes = admin_notes
    venue_request.reviewed_at = timezone.now()
    venue_request.save(update_fields=["status", "admin_notes", "reviewed_at"])
    return venue_request


def fulfil_venue_request(venue_request: VenueRequest) -> VenueRequest:
    with transaction.atomic():
        return _fulfil_locked(venue_request)


def _fulfil_locked(venue_request: VenueRequest) -> VenueRequest:
    venue_request.refresh_from_db(
        from_queryset=VenueRequest.objects.select_for_update()
    )
    if venue_request.status != VenueRequest.Status.PENDING:
        raise VenueRequestNotPendingError(
            "Only pending venue requests can be fulfilled "
            f"(current status: {venue_request.get_status_display()})."
        )
    venue_request.status = VenueRequest.Status.FULFILLED
    venue_request.reviewed_at = timezone.now()
    venue_request.save(update_fields=["status", "reviewed_at"])
    return venue_request
