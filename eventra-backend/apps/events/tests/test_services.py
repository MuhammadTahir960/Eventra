from datetime import timedelta
from unittest.mock import MagicMock

import pytest
from django.db import IntegrityError
from django.utils import timezone

from apps.bookings.factories import BookingFactory
from apps.bookings.models import Booking
from apps.categories.factories import CategoryFactory
from apps.common.constants import Roles
from apps.payouts.factories import OrganizerPayoutFactory
from apps.seating.factories import EventSeatFactory
from apps.seating.models import EventSeat
from apps.tickets.models import Ticket
from apps.users.factories import UserFactory
from apps.venues.factories import VenueFactory

from ..factories import EventFactory, TicketTierFactory
from ..models import Event
from ..services import (
    MAX_EVENT_LENGTH_DAYS,
    RUNNING_LATE_OPENS_HOURS,
    DuplicateEventSlugError,
    EventEndNotExtendableError,
    EventNotCancellableError,
    EventNotDeletableError,
    InvalidEventEndError,
    TierPriceImmutableError,
    cancel_event,
    complete_past_events,
    ensure_can_restore_event,
    ensure_event_deletable,
    ensure_tier_price_mutable,
    extend_event_end,
    find_blocking_upcoming_event,
    resolve_create_status,
    should_retrigger_approval,
    should_retrigger_approval_for_tier,
    visible_events_for_ticket_holder,
    visible_events_for_user,
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
    inactive = EventFactory(title="Shared Title", slug="shared-title")
    inactive.is_active = False
    inactive.save(update_fields=["is_active"])
    EventFactory(title="Shared Title", slug="shared-title")

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


# ==================================================
# manual payouts: completion, void, delete, running late
# ==================================================


def _sell_ticket(event):
    booking = BookingFactory(status=Booking.Status.CONFIRMED)
    seat = EventSeatFactory(event=event, status=EventSeat.Status.BOOKED)
    Ticket.objects.create(booking=booking, event_seat=seat, status=Ticket.Status.VALID)
    return booking


def test_completion_records_completed_at():
    start, end = _past(hours_ago=3)
    event = EventFactory(
        status=Event.Status.APPROVED, start_datetime=start, end_datetime=end
    )
    complete_past_events()
    event.refresh_from_db()
    assert event.completed_at is not None


def test_event_in_review_with_sales_completes():
    start, end = _past(hours_ago=3)
    event = EventFactory(
        status=Event.Status.PENDING_APPROVAL, start_datetime=start, end_datetime=end
    )
    _sell_ticket(event)
    assert complete_past_events() == 1
    event.refresh_from_db()
    assert event.status == Event.Status.COMPLETED


def test_event_completed_in_review_stays_hidden_from_the_public():
    start, end = _past(hours_ago=3)
    event = EventFactory(
        status=Event.Status.PENDING_APPROVAL, start_datetime=start, end_datetime=end
    )
    buyer = _sell_ticket(event).user
    complete_past_events()
    event.refresh_from_db()
    assert event.completed_in_review is True

    assert not visible_events_for_user(None).filter(pk=event.pk).exists()
    stranger = UserFactory(role=Roles.ATTENDEE)
    assert not visible_events_for_ticket_holder(stranger).filter(pk=event.pk).exists()
    assert visible_events_for_ticket_holder(buyer).filter(pk=event.pk).exists()
    assert visible_events_for_user(event.organizer).filter(pk=event.pk).exists()


def test_approved_event_completes_publicly():
    start, end = _past(hours_ago=3)
    event = EventFactory(
        status=Event.Status.APPROVED, start_datetime=start, end_datetime=end
    )
    complete_past_events()
    event.refresh_from_db()
    assert event.completed_in_review is False
    assert visible_events_for_user(None).filter(pk=event.pk).exists()


def test_event_in_review_without_sales_stays_in_review():
    start, end = _past(hours_ago=3)
    event = EventFactory(
        status=Event.Status.PENDING_APPROVAL, start_datetime=start, end_datetime=end
    )
    assert complete_past_events() == 0
    event.refresh_from_db()
    assert event.status == Event.Status.PENDING_APPROVAL


def test_completed_event_needs_completed_at():
    with pytest.raises(IntegrityError):
        EventFactory(status=Event.Status.COMPLETED, completed_at=None)


def test_completed_unpaid_event_with_sales_cannot_be_deleted():
    event = EventFactory(status=Event.Status.COMPLETED)
    _sell_ticket(event)
    with pytest.raises(EventNotDeletableError, match="paid out"):
        ensure_event_deletable(event)


def test_completed_event_can_be_deleted_once_paid_out():
    event = EventFactory(status=Event.Status.COMPLETED)
    _sell_ticket(event)
    OrganizerPayoutFactory(event=event)
    ensure_event_deletable(event)


def test_only_an_admin_may_void_a_completed_event():
    event = EventFactory(status=Event.Status.COMPLETED)
    with pytest.raises(EventNotCancellableError, match="Only an admin"):
        cancel_event(event)
    cancel_event(event, allow_completed=True)
    event.refresh_from_db()
    assert event.status == Event.Status.CANCELLED


def test_a_paid_out_event_cannot_be_voided():
    event = EventFactory(status=Event.Status.COMPLETED)
    OrganizerPayoutFactory(event=event)
    with pytest.raises(EventNotCancellableError, match="paid out"):
        cancel_event(event, allow_completed=True)


def _running(**kwargs):
    now = timezone.now()
    return EventFactory(
        start_datetime=now - timedelta(hours=2),
        end_datetime=now + timedelta(minutes=30),
        **kwargs,
    )


def test_running_late_moves_the_end_without_review():
    event = _running(status=Event.Status.APPROVED)
    new_end = event.end_datetime + timedelta(hours=2)
    extend_event_end(event, new_end)
    event.refresh_from_db()
    assert event.end_datetime == new_end
    assert event.status == Event.Status.APPROVED


@pytest.mark.parametrize(
    "shift",
    [timedelta(0), -timedelta(minutes=10), timedelta(days=MAX_EVENT_LENGTH_DAYS)],
)
def test_running_late_rejects_earlier_or_too_far(shift):
    event = _running(status=Event.Status.APPROVED)
    with pytest.raises(InvalidEventEndError):
        extend_event_end(event, event.end_datetime + shift)


@pytest.mark.parametrize(
    "status", [Event.Status.COMPLETED, Event.Status.CANCELLED, Event.Status.REJECTED]
)
def test_running_late_refused_for_finished_events(status):
    event = _running(status=status)
    with pytest.raises(EventEndNotExtendableError):
        extend_event_end(event, event.end_datetime + timedelta(hours=1))


def test_running_late_emails_holders_only_when_the_day_changes(
    monkeypatch, django_capture_on_commit_callbacks
):
    task = MagicMock()
    monkeypatch.setattr("apps.notifications.tasks.send_event_running_late_email", task)
    midnight = (timezone.now() + timedelta(hours=27)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    event = EventFactory(
        status=Event.Status.APPROVED,
        start_datetime=midnight - timedelta(hours=3),
        end_datetime=midnight - timedelta(hours=1),
    )
    booking = _sell_ticket(event)

    with django_capture_on_commit_callbacks(execute=True):
        extend_event_end(event, midnight - timedelta(minutes=30))
    task.delay.assert_not_called()

    with django_capture_on_commit_callbacks(execute=True):
        extend_event_end(event, midnight + timedelta(hours=3))
    task.delay.assert_called_once_with(str(event.id), str(booking.user_id))


def test_running_late_is_closed_until_a_day_before_the_start():
    start = timezone.now() + timedelta(hours=RUNNING_LATE_OPENS_HOURS + 2)
    event = EventFactory(
        status=Event.Status.APPROVED,
        start_datetime=start,
        end_datetime=start + timedelta(hours=2),
    )
    with pytest.raises(EventEndNotExtendableError, match="opens"):
        extend_event_end(event, event.end_datetime + timedelta(hours=1))
    event.refresh_from_db()
    assert event.end_datetime == start + timedelta(hours=2)


def test_a_long_festival_can_run_late_up_to_the_length_limit():
    now = timezone.now()
    event = EventFactory(
        status=Event.Status.APPROVED,
        start_datetime=now + timedelta(hours=1),
        end_datetime=now + timedelta(days=10),
    )
    extend_event_end(event, now + timedelta(days=10, hours=2))
    with pytest.raises(InvalidEventEndError, match="14 days"):
        extend_event_end(event, now + timedelta(days=15))
