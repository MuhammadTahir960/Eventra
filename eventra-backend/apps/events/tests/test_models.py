from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.categories.factories import CategoryFactory
from apps.venues.factories import VenueFactory

from ..factories import EventFactory, TicketTierFactory, TierSectionMappingFactory
from ..models import Event, TicketTier

pytestmark = pytest.mark.django_db


# ==================================================
# Slug generation
# ==================================================


def test_slug_generated_on_create():
    event = EventFactory(title="Summer Music Festival")
    assert event.slug == "summer-music-festival"


def test_slug_frozen_after_creation_even_when_title_changes():
    event = EventFactory(title="Old Title")
    original_slug = event.slug
    event.title = "New Title"
    event.save()
    assert event.slug == original_slug


def test_slug_not_regenerated_when_title_unchanged():
    event = EventFactory(title="Stable Title")
    original_slug = event.slug
    event.description = "Updated description only."
    event.save()
    assert event.slug == original_slug


def test_explicit_slug_is_not_overwritten_on_create():
    from apps.categories.factories import CategoryFactory
    from apps.users.factories import UserFactory
    from apps.venues.factories import VenueFactory

    event = EventFactory.build(
        title="Some Title",
        slug="custom-slug",
        venue=VenueFactory(),
        category=CategoryFactory(),
        organizer=UserFactory(),
    )
    event.save()
    assert event.slug == "custom-slug"


# ==================================================
# Constraints
# ==================================================


def test_duplicate_active_slug_rejected_at_db_level():
    EventFactory(title="Popular Event")
    with pytest.raises(IntegrityError), transaction.atomic():
        EventFactory(title="Popular Event")


def test_duplicate_slug_allowed_if_original_is_soft_deleted():
    original = EventFactory(title="Reusable Title")
    original.is_active = False
    original.save(update_fields=["is_active"])
    EventFactory(title="Reusable Title")


def test_end_datetime_before_start_datetime_rejected_at_db_level():
    now = timezone.now()
    with pytest.raises(IntegrityError), transaction.atomic():
        EventFactory(start_datetime=now, end_datetime=now - timedelta(hours=1))


def test_end_datetime_equal_to_start_datetime_rejected_at_db_level():
    now = timezone.now()
    with pytest.raises(IntegrityError), transaction.atomic():
        EventFactory(start_datetime=now, end_datetime=now)


# ==================================================
# Soft delete / manager behavior
# ==================================================


def test_default_manager_excludes_inactive_events():
    active = EventFactory(title="Active Event")
    inactive = EventFactory(title="Inactive Event")
    inactive.is_active = False
    inactive.save(update_fields=["is_active"])

    ids = set(Event.objects.values_list("id", flat=True))
    assert active.id in ids
    assert inactive.id not in ids


def test_all_objects_includes_inactive_events():
    inactive = EventFactory(title="Inactive Event")
    inactive.is_active = False
    inactive.save(update_fields=["is_active"])

    assert Event.all_objects.filter(id=inactive.id).exists()


# ==================================================
# FK on_delete behavior
# ==================================================


def test_hard_deleting_venue_sets_event_venue_to_null():
    venue = VenueFactory()
    event = EventFactory(venue=venue)
    venue.delete()
    event.refresh_from_db()
    assert event.venue_id is None
    assert Event.all_objects.filter(id=event.id).exists()


def test_hard_deleting_category_sets_event_category_to_null():
    category = CategoryFactory()
    event = EventFactory(category=category)
    category.delete()
    event.refresh_from_db()
    assert event.category_id is None


def test_deleting_organizer_is_blocked_while_events_exist():
    event = EventFactory()
    organizer = event.organizer
    with pytest.raises(IntegrityError), transaction.atomic():
        organizer.delete()


def test_hard_deleting_event_cascades_to_ticket_tiers():
    tier = TicketTierFactory()
    event = tier.event
    event.delete()
    assert not TicketTier.objects.filter(id=tier.id).exists()


def test_hard_deleting_ticket_tier_cascades_to_section_mappings():
    mapping = TierSectionMappingFactory()
    tier = mapping.ticket_tier
    tier.delete()
    assert not tier.section_mappings.model.objects.filter(id=mapping.id).exists()


# ==================================================
# TicketTier
# ==================================================


def test_ticket_tier_price_must_be_positive():
    tier = TicketTierFactory.build(price="0.00")
    with pytest.raises(ValidationError):
        tier.full_clean()


# ==================================================
# TierSectionMapping
# ==================================================


def test_duplicate_section_for_same_event_rejected_at_db_level():
    tier = TicketTierFactory()
    TierSectionMappingFactory(event=tier.event, ticket_tier=tier, section="A")
    with pytest.raises(IntegrityError), transaction.atomic():
        TierSectionMappingFactory(event=tier.event, ticket_tier=tier, section="A")


def test_same_section_label_allowed_across_different_events():
    TierSectionMappingFactory(section="A")
    TierSectionMappingFactory(section="A")
