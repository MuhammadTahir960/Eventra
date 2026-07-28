import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from ..models import Seat, Venue
from ..factories import SeatFactory, VenueFactory

pytestmark = pytest.mark.django_db


# ==================================================
# Venue — uniqueness constraint (name+city, active only)
# ==================================================


def test_duplicate_name_and_city_case_insensitive_rejected_at_db_level():
    VenueFactory(name="Arena One", city="Nairobi")
    with pytest.raises(IntegrityError):
        VenueFactory(name="ARENA one", city="NAIROBI")


def test_same_name_different_city_allowed():
    VenueFactory(name="Arena One", city="Nairobi")
    VenueFactory(name="Arena One", city="Mombasa")


def test_same_name_and_city_allowed_when_original_is_soft_deleted():
    original = VenueFactory(name="Arena One", city="Nairobi", is_active=False)
    VenueFactory(name="Arena One", city="Nairobi")
    original.refresh_from_db()
    assert original.is_active is False


# ==================================================
# Venue — field validators
# ==================================================


def test_name_shorter_than_two_chars_fails_full_clean():
    venue = Venue(
        name="A", address="1 St", city="Nairobi", country="Kenya", capacity=10
    )
    with pytest.raises(ValidationError):
        venue.full_clean()


def test_name_of_exactly_two_chars_passes_full_clean():
    venue = Venue(
        name="Ab", address="1 St", city="Nairobi", country="Kenya", capacity=10
    )
    venue.full_clean()


def test_capacity_of_zero_fails_full_clean():
    venue = Venue(
        name="Valid Name", address="1 St", city="Nairobi", country="Kenya", capacity=0
    )
    with pytest.raises(ValidationError):
        venue.full_clean()


def test_negative_capacity_fails_full_clean():
    venue = Venue(
        name="Valid Name", address="1 St", city="Nairobi", country="Kenya", capacity=-5
    )
    with pytest.raises(ValidationError):
        venue.full_clean()


def test_capacity_of_one_passes_full_clean():
    venue = Venue(
        name="Valid Name", address="1 St", city="Nairobi", country="Kenya", capacity=1
    )
    venue.full_clean()


# ==================================================
# Venue — soft delete manager behavior
# ==================================================


def test_default_manager_excludes_inactive_venues():
    VenueFactory(is_active=True)
    VenueFactory(is_active=False)
    assert Venue.objects.count() == 1


def test_all_objects_manager_includes_inactive_venues():
    VenueFactory(is_active=True)
    VenueFactory(is_active=False)
    assert Venue.all_objects.count() == 2


# ==================================================
# Venue — misc
# ==================================================


def test_str_includes_name_city_and_country():
    venue = VenueFactory(name="Kasarani Stadium", city="Nairobi", country="Kenya")
    text = str(venue)
    assert "Kasarani Stadium" in text
    assert "Nairobi" in text
    assert "Kenya" in text


def test_default_ordering_is_by_name():
    VenueFactory(name="Zebra Arena")
    VenueFactory(name="Alpha Arena")
    names = list(Venue.objects.values_list("name", flat=True))
    assert names == sorted(names)


# ==================================================
# Seat — uniqueness constraint per venue
# ==================================================


def test_duplicate_seat_same_venue_section_row_number_rejected():
    venue = VenueFactory()
    SeatFactory(venue=venue, section="A", row_label="1", seat_number=5)
    with pytest.raises(IntegrityError):
        SeatFactory(venue=venue, section="A", row_label="1", seat_number=5)


def test_same_section_row_number_allowed_across_different_venues():
    SeatFactory(section="A", row_label="1", seat_number=5)
    SeatFactory(section="A", row_label="1", seat_number=5)


def test_seat_cascades_on_venue_hard_delete():
    venue = VenueFactory()
    SeatFactory(venue=venue)
    venue.delete()
    assert Seat.objects.count() == 0


def test_seat_str_includes_venue_section_row_and_number():
    seat = SeatFactory(section="B", row_label="2", seat_number=10)
    text = str(seat)
    assert "B" in text
    assert "2" in text
    assert "10" in text
