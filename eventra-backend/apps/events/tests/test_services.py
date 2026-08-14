from datetime import timedelta

import pytest
from django.utils import timezone

from apps.categories.factories import CategoryFactory
from apps.common.constants import Roles
from apps.seating.factories import EventSeatFactory
from apps.users.factories import UserFactory
from apps.venues.factories import VenueFactory

from ..factories import EventFactory, TicketTierFactory
from ..models import Event
from ..services import (
    DuplicateEventSlugError,
    EventNotDeletableError,
    TierPriceImmutableError,
    complete_past_events,
    ensure_can_restore_event,
    ensure_event_deletable,
    ensure_tier_price_mutable,
    find_blocking_upcoming_event,
    resolve_create_status,
    should_retrigger_approval,
    should_retrigger_approval_for_tier,
)

pytestmark = pytest.mark.django_db


# ==================================================
# ensure_event_deletable
# ==================================================


@pytest.mark.parametrize("status", [Event.Status.CANCELLED, Event.Status.COMPLETED])
def test_ensure_event_deletable_allows_terminal_statuses(status):
    event = EventFactory(status=status)
    ensure_event_deletable(event)


@pytest.mark.parametrize(
    "status",
    [Event.Status.PENDING_APPROVAL, Event.Status.APPROVED, Event.Status.REJECTED],
)
def test_ensure_event_deletable_blocks_non_terminal_statuses(status):
    event = EventFactory(status=status)
    with pytest.raises(EventNotDeletableError):
        ensure_event_deletable(event)


# ==================================================
# ensure_tier_price_mutable
# ==================================================


def test_ensure_tier_price_mutable_allows_when_no_seats_instantiated():
    tier = TicketTierFactory()
    ensure_tier_price_mutable(tier)


def test_ensure_tier_price_mutable_blocks_when_event_seats_exist():
    tier = TicketTierFactory()
    EventSeatFactory(event=tier.event, ticket_tier=tier)

    with pytest.raises(TierPriceImmutableError):
        ensure_tier_price_mutable(tier)


# ==================================================
# resolve_create_status
# ==================================================


def test_resolve_create_status_admin_gets_approved():
    admin = UserFactory(role=Roles.ADMIN)
    assert resolve_create_status(admin) == Event.Status.APPROVED


def test_resolve_create_status_organizer_gets_pending():
    organizer = UserFactory(role=Roles.ORGANIZER)
    assert resolve_create_status(organizer) == Event.Status.PENDING_APPROVAL


# ==================================================
# should_retrigger_approval
# ==================================================


def test_should_retrigger_approval_true_for_organizer_sensitive_field():
    event = EventFactory(organizer=UserFactory(role=Roles.ORGANIZER))
    assert should_retrigger_approval(event=event, changed_fields={"venue"}) is True


def test_should_retrigger_approval_false_for_organizer_cosmetic_field_only():
    event = EventFactory(organizer=UserFactory(role=Roles.ORGANIZER))
    assert (
        should_retrigger_approval(event=event, changed_fields={"title", "description"})
        is False
    )


def test_should_retrigger_approval_false_for_admin_regardless_of_fields():
    event = EventFactory(organizer=UserFactory(role=Roles.ADMIN))
    assert (
        should_retrigger_approval(
            event=event, changed_fields={"venue", "start_datetime"}
        )
        is False
    )


def test_should_retrigger_approval_false_when_no_fields_changed():
    event = EventFactory(organizer=UserFactory(role=Roles.ORGANIZER))
    assert should_retrigger_approval(event=event, changed_fields=set()) is False


# ==================================================
# should_retrigger_approval_for_tier
# ==================================================


def test_should_retrigger_approval_for_tier_true_for_organizer():
    tier = TicketTierFactory(
        event=EventFactory(organizer=UserFactory(role=Roles.ORGANIZER))
    )
    assert should_retrigger_approval_for_tier(tier) is True


def test_should_retrigger_approval_for_tier_false_for_admin():
    tier = TicketTierFactory(
        event=EventFactory(organizer=UserFactory(role=Roles.ADMIN))
    )
    assert should_retrigger_approval_for_tier(tier) is False


# ==================================================
# ensure_can_restore_event
# ==================================================


def test_ensure_can_restore_event_allows_when_no_conflict():
    event = EventFactory(title="Unique Title")
    event.is_active = False
    event.save(update_fields=["is_active"])
    ensure_can_restore_event(event)  # should not raise


def test_ensure_can_restore_event_blocks_active_slug_collision():
    inactive = EventFactory(title="Shared Title")
    inactive.is_active = False
    inactive.save(update_fields=["is_active"])
    EventFactory(title="Shared Title")

    with pytest.raises(DuplicateEventSlugError):
        ensure_can_restore_event(inactive)


# ==================================================
# find_blocking_upcoming_event
# ==================================================


def test_find_blocking_upcoming_event_true_for_upcoming_approved_event():
    venue = VenueFactory()
    EventFactory(
        venue=venue,
        status=Event.Status.APPROVED,
        start_datetime=timezone.now() + timedelta(days=1),
    )
    assert find_blocking_upcoming_event(venue_id=venue.id) is True


@pytest.mark.parametrize(
    "status",
    [Event.Status.PENDING_APPROVAL, Event.Status.REJECTED, Event.Status.CANCELLED],
)
def test_find_blocking_upcoming_event_false_for_non_blocking_statuses(status):
    venue = VenueFactory()
    EventFactory(
        venue=venue, status=status, start_datetime=timezone.now() + timedelta(days=1)
    )
    assert find_blocking_upcoming_event(venue_id=venue.id) is False


def test_find_blocking_upcoming_event_false_for_past_event():
    venue = VenueFactory()
    EventFactory(
        venue=venue,
        status=Event.Status.COMPLETED,
        start_datetime=timezone.now() - timedelta(days=10),
        end_datetime=timezone.now() - timedelta(days=9),
    )
    assert find_blocking_upcoming_event(venue_id=venue.id) is False


def test_find_blocking_upcoming_event_false_with_no_ids_given():
    assert find_blocking_upcoming_event() is False


def test_find_blocking_upcoming_event_scopes_to_category_independently():
    category = CategoryFactory()
    EventFactory(
        category=category,
        status=Event.Status.APPROVED,
        start_datetime=timezone.now() + timedelta(days=1),
    )
    assert find_blocking_upcoming_event(category_id=category.id) is True
    assert (
        find_blocking_upcoming_event(venue_id=None, category_id=CategoryFactory().id)
        is False
    )


# ---- complete_past_events ----


def _past(hours_ago):
    end = timezone.now() - timedelta(hours=hours_ago)
    return end - timedelta(hours=3), end


def test_completes_approved_event_past_the_buffer():
    start, end = _past(hours_ago=3)
    event = EventFactory(
        status=Event.Status.APPROVED, start_datetime=start, end_datetime=end
    )
    original_updated_at = event.updated_at
    count = complete_past_events()
    event.refresh_from_db()
    assert count == 1
    assert event.status == Event.Status.COMPLETED
    assert event.updated_at > original_updated_at


def test_does_not_complete_event_still_within_buffer():
    # Ended 1 hour ago — inside the 2-hour breathing-room window.
    start, end = _past(hours_ago=1)
    event = EventFactory(
        status=Event.Status.APPROVED, start_datetime=start, end_datetime=end
    )
    count = complete_past_events()
    event.refresh_from_db()
    assert count == 0
    assert event.status == Event.Status.APPROVED


def test_does_not_complete_future_event():
    event = EventFactory(status=Event.Status.APPROVED)  # factory default: +7 days
    count = complete_past_events()
    event.refresh_from_db()
    assert count == 0
    assert event.status == Event.Status.APPROVED


@pytest.mark.parametrize(
    "status",
    [
        Event.Status.PENDING_APPROVAL,
        Event.Status.REJECTED,
        Event.Status.CANCELLED,
        Event.Status.COMPLETED,
    ],
)
def test_only_approved_status_is_swept(status):
    start, end = _past(hours_ago=3)
    event = EventFactory(status=status, start_datetime=start, end_datetime=end)
    complete_past_events()
    event.refresh_from_db()
    assert event.status == status


def test_returns_count_of_events_completed():
    start, end = _past(hours_ago=3)
    EventFactory(status=Event.Status.APPROVED, start_datetime=start, end_datetime=end)
    EventFactory(status=Event.Status.APPROVED, start_datetime=start, end_datetime=end)
    EventFactory(status=Event.Status.APPROVED)
    assert complete_past_events() == 2
