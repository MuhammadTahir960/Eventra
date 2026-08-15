import pytest

from apps.events.factories import EventFactory, TicketTierFactory
from apps.seating.factories import EventSeatFactory

from ..factories import SeatFactory, VenueFactory
from ..models import Seat
from ..services import (
    CapacityExceededError,
    DuplicateSeatError,
    SeatTemplateExistsError,
    SeatTemplateInUseError,
    bulk_create_seat_template,
)

pytestmark = pytest.mark.django_db


def _sections(*, section_count=1, rows_per_section=2, seats_per_row=5):
    return [
        {
            "name": f"Section {s}",
            "rows": [
                {"row_label": f"R{r}", "seat_count": seats_per_row}
                for r in range(rows_per_section)
            ],
        }
        for s in range(section_count)
    ]


# ==================================================
# Happy path
# ==================================================


def test_creates_expected_number_of_seats():
    venue = VenueFactory(capacity=100)
    sections = _sections(section_count=2, rows_per_section=2, seats_per_row=5)

    created = bulk_create_seat_template(venue=venue, sections=sections)

    assert len(created) == 20
    assert venue.seats.count() == 20


def test_seat_numbers_start_at_one_and_are_sequential_per_row():
    venue = VenueFactory(capacity=50)
    sections = [{"name": "A", "rows": [{"row_label": "1", "seat_count": 3}]}]

    bulk_create_seat_template(venue=venue, sections=sections)

    numbers = sorted(
        Seat.objects.filter(venue=venue, section="A", row_label="1").values_list(
            "seat_number", flat=True
        )
    )
    assert numbers == [1, 2, 3]


# ==================================================
# SeatTemplateExistsError
# ==================================================


def test_rejects_reseed_by_default_when_seats_already_exist():
    venue = VenueFactory(capacity=50)
    SeatFactory(venue=venue)

    with pytest.raises(SeatTemplateExistsError):
        bulk_create_seat_template(venue=venue, sections=_sections())


def test_existing_seats_untouched_after_rejected_reseed_attempt():
    venue = VenueFactory(capacity=50)
    SeatFactory(venue=venue, section="Original", row_label="1", seat_number=1)

    with pytest.raises(SeatTemplateExistsError):
        bulk_create_seat_template(venue=venue, sections=_sections())

    assert venue.seats.count() == 1
    assert venue.seats.first().section == "Original"


def test_allow_reseed_true_replaces_existing_seats():
    venue = VenueFactory(capacity=50)
    SeatFactory(venue=venue, section="Original", row_label="1", seat_number=1)

    created = bulk_create_seat_template(
        venue=venue, sections=_sections(), allow_reseed=True
    )

    assert venue.seats.count() == len(created)
    assert not venue.seats.filter(section="Original").exists()


def test_allow_reseed_true_with_no_existing_seats_behaves_like_normal_create():
    venue = VenueFactory(capacity=50)
    created = bulk_create_seat_template(
        venue=venue, sections=_sections(), allow_reseed=True
    )
    assert len(created) == venue.seats.count()


# ==================================================
# SeatTemplateInUseError
# ==================================================


def test_reseed_blocked_when_a_seat_already_has_an_instantiated_event_seat():
    venue = VenueFactory(capacity=50)
    seat = SeatFactory(venue=venue, section="Original", row_label="1", seat_number=1)
    event = EventFactory(venue=venue)
    tier = TicketTierFactory(event=event)
    EventSeatFactory(event=event, seat=seat, ticket_tier=tier)

    with pytest.raises(SeatTemplateInUseError):
        bulk_create_seat_template(venue=venue, sections=_sections(), allow_reseed=True)

    assert venue.seats.count() == 1
    assert venue.seats.first().id == seat.id


def test_reseed_allowed_once_the_in_use_seat_has_no_event_seats():
    venue = VenueFactory(capacity=50)
    SeatFactory(venue=venue, section="Original", row_label="1", seat_number=1)

    created = bulk_create_seat_template(
        venue=venue, sections=_sections(), allow_reseed=True
    )
    assert venue.seats.count() == len(created)


# ==================================================
# CapacityExceededError
# ==================================================


def test_rejects_payload_that_exceeds_capacity():
    venue = VenueFactory(capacity=5)
    sections = [{"name": "A", "rows": [{"row_label": "1", "seat_count": 6}]}]

    with pytest.raises(CapacityExceededError):
        bulk_create_seat_template(venue=venue, sections=sections)


def test_payload_exactly_at_capacity_is_allowed():
    venue = VenueFactory(capacity=6)
    sections = [{"name": "A", "rows": [{"row_label": "1", "seat_count": 6}]}]

    created = bulk_create_seat_template(venue=venue, sections=sections)
    assert len(created) == 6


def test_no_seats_created_when_capacity_exceeded():
    venue = VenueFactory(capacity=5)
    sections = [{"name": "A", "rows": [{"row_label": "1", "seat_count": 6}]}]

    with pytest.raises(CapacityExceededError):
        bulk_create_seat_template(venue=venue, sections=sections)

    assert venue.seats.count() == 0


def test_capacity_check_applies_to_reseed_too():
    venue = VenueFactory(capacity=5)
    SeatFactory(venue=venue)
    sections = [{"name": "A", "rows": [{"row_label": "1", "seat_count": 6}]}]

    with pytest.raises(CapacityExceededError):
        bulk_create_seat_template(venue=venue, sections=sections, allow_reseed=True)


# ==================================================
# DuplicateSeatError
# ==================================================


def test_duplicate_seats_within_payload_raise_duplicate_seat_error():
    venue = VenueFactory(capacity=50)
    sections = [
        {"name": "A", "rows": [{"row_label": "1", "seat_count": 3}]},
        {"name": "A", "rows": [{"row_label": "1", "seat_count": 3}]},
    ]

    with pytest.raises(DuplicateSeatError):
        bulk_create_seat_template(venue=venue, sections=sections)


def test_duplicate_seat_error_leaves_no_partial_seats_behind():
    venue = VenueFactory(capacity=50)
    sections = [
        {"name": "A", "rows": [{"row_label": "1", "seat_count": 3}]},
        {"name": "A", "rows": [{"row_label": "1", "seat_count": 3}]},
    ]

    with pytest.raises(DuplicateSeatError):
        bulk_create_seat_template(venue=venue, sections=sections)

    assert venue.seats.count() == 0
