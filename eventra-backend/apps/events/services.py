from datetime import timedelta

from django.db import transaction
from django.db.models import Q, QuerySet
from django.utils import timezone
from rest_framework.generics import get_object_or_404

from apps.bookings.models import Booking
from apps.common.constants import Roles

from .models import Event, TicketTier


class EventNotDeletableError(Exception):
    """Raised when an event's status doesn't allow deletion (soft or hard)."""


class TierPriceImmutableError(Exception):
    """Raised when a ticket tier's price is edited after seats have been instantiated against it."""


class DuplicateEventSlugError(Exception):
    """Raised when restoring an event would collide with an active event's slug."""


class EventNotPendingApprovalError(Exception):
    """Raised when approve/reject is attempted on an event not awaiting approval."""


class EventRejectionReasonRequiredError(Exception):
    """Raised when POST /admin/events/{id}/reject/ is called with no (or blank) reason."""


class EventNotCancellableError(Exception):
    """Raised when cancel is attempted on an event that's completed or already cancelled."""


class EventHasPaidBookingsError(Exception):
    """Raised when rejecting an event that already has confirmed bookings."""


class SeatMapLockedError(Exception):
    """Raised when a section is mapped to a tier after the event's seats were created."""


PUBLIC_STATUSES = [Event.Status.APPROVED, Event.Status.COMPLETED]
DELETABLE_STATUSES = {Event.Status.CANCELLED, Event.Status.COMPLETED}
SENSITIVE_EVENT_FIELDS = frozenset(
    {"venue", "category", "start_datetime", "end_datetime"}
)
COMPLETE_PAST_EVENTS_BUFFER_HOURS = 2


def ensure_event_deletable(event: Event) -> None:
    if event.status not in DELETABLE_STATUSES:
        raise EventNotDeletableError(
            "Event must be cancelled or completed before it can be deleted "
            f"(current status: {event.get_status_display()})."
        )


class EventNotEditableError(Exception):
    """Raised when an edit targets a cancelled or completed (terminal) event."""


def ensure_event_editable(event: Event) -> None:
    if event.status in (Event.Status.COMPLETED, Event.Status.CANCELLED):
        raise EventNotEditableError(
            f"A {event.get_status_display().lower()} event can no longer be edited."
        )


def ensure_tier_price_mutable(tier: TicketTier) -> None:
    if hasattr(tier, "event_seats") and tier.event_seats.exists():
        raise TierPriceImmutableError(
            "Price is immutable once seats have been instantiated for this tier."
        )


def ensure_sections_mappable(event: Event) -> None:
    if event.event_seats.exists():
        raise SeatMapLockedError(
            "Seats have already been created for this event, "
            "so sections can no longer be mapped to tiers."
        )


def resolve_create_status(actor) -> str:
    return (
        Event.Status.APPROVED
        if actor.role == Roles.ADMIN
        else Event.Status.PENDING_APPROVAL
    )


def should_retrigger_approval(*, event: Event, changed_fields: set[str]) -> bool:
    if event.organizer.role == Roles.ADMIN:
        return False
    return bool(SENSITIVE_EVENT_FIELDS & changed_fields)


def should_retrigger_approval_for_tier(tier: TicketTier) -> bool:
    return tier.event.organizer.role != Roles.ADMIN


MAX_REJECTION_REASON_LENGTH = 2000


def paid_bookings(event) -> QuerySet:
    return Booking.objects.filter(
        tickets__event_seat__event=event, status=Booking.Status.CONFIRMED
    )


def _lock(event: Event) -> None:
    event.refresh_from_db(from_queryset=Event.all_objects.select_for_update())


def approve_event(event: Event) -> Event:
    with transaction.atomic():
        return _approve_locked(event)


def _approve_locked(event: Event) -> Event:
    _lock(event)
    if event.status != Event.Status.PENDING_APPROVAL:
        raise EventNotPendingApprovalError(
            "Only events awaiting approval can be approved "
            f"(current status: {event.get_status_display()})."
        )
    event.status = Event.Status.APPROVED
    event.rejection_reason = ""
    event.save(update_fields=["status", "rejection_reason", "updated_at"])
    _email_buyers_on_commit("send_event_updated_email", event, _paid_buyer_ids(event))
    return event


def _paid_buyer_ids(event: Event) -> list[str]:
    return [
        str(user_id)
        for user_id in paid_bookings(event)
        .order_by()
        .values_list("user_id", flat=True)
        .distinct()
    ]


def _email_buyers_on_commit(task_name: str, event: Event, user_ids: list[str]) -> None:
    if not user_ids:
        return
    event_id = str(event.id)

    def enqueue():
        from apps.notifications import tasks

        task = getattr(tasks, task_name)
        for user_id in user_ids:
            task.delay(event_id, user_id)

    transaction.on_commit(enqueue, robust=True)


def reject_event(event: Event, reason: str) -> Event:
    with transaction.atomic():
        return _reject_locked(event, reason)


def _reject_locked(event: Event, reason: str) -> Event:
    _lock(event)
    if event.status != Event.Status.PENDING_APPROVAL:
        raise EventNotPendingApprovalError(
            "Only events awaiting approval can be rejected "
            f"(current status: {event.get_status_display()})."
        )
    reason = (reason if isinstance(reason, str) else "").strip()
    if not reason:
        raise EventRejectionReasonRequiredError(
            "A non-empty 'reason' is required to reject an event."
        )
    if len(reason) > MAX_REJECTION_REASON_LENGTH:
        raise EventRejectionReasonRequiredError(
            f"'reason' must be at most {MAX_REJECTION_REASON_LENGTH} characters."
        )
    if paid_bookings(event).exists():
        raise EventHasPaidBookingsError(
            "This event has paid bookings. Cancel it instead so attendees are refunded."
        )
    event.status = Event.Status.REJECTED
    event.rejection_reason = reason
    event.save(update_fields=["status", "rejection_reason", "updated_at"])
    return event


def cancel_event(event: Event) -> Event:
    with transaction.atomic():
        return _cancel_locked(event)


def _cancel_locked(event: Event) -> Event:
    _lock(event)
    if event.status == Event.Status.COMPLETED:
        raise EventNotCancellableError(
            "Event is completed and can no longer be cancelled."
        )
    if event.status == Event.Status.CANCELLED:
        raise EventNotCancellableError("Event is already cancelled.")

    buyer_ids = _paid_buyer_ids(event)
    event.status = Event.Status.CANCELLED
    event.save(update_fields=["status", "updated_at"])
    _email_buyers_on_commit("send_event_cancelled_email", event, buyer_ids)
    return event


def ensure_can_restore_event(event: Event) -> None:
    conflict = Event.objects.filter(slug=event.slug).exclude(pk=event.pk).exists()
    if conflict:
        raise DuplicateEventSlugError(
            "Cannot restore: an active event with this slug already exists."
        )


def visible_events_for_user(user) -> QuerySet:
    qs = Event.objects.select_related(
        "venue", "category", "organizer", "league", "home_team", "away_team"
    )
    if not user or not user.is_authenticated:
        return qs.filter(status__in=PUBLIC_STATUSES)
    if user.role == Roles.ADMIN:
        return qs
    if user.role == Roles.ORGANIZER:
        return qs.filter(Q(organizer=user) | Q(status__in=PUBLIC_STATUSES))
    return qs.filter(status__in=PUBLIC_STATUSES)


def visible_events_for_ticket_holder(user) -> QuerySet:
    qs = visible_events_for_user(user)
    if not user or not user.is_authenticated or user.role == Roles.ADMIN:
        return qs
    held = Booking.objects.filter(user=user, status=Booking.Status.CONFIRMED).values(
        "tickets__event_seat__event"
    )
    return qs | Event.objects.filter(status=Event.Status.PENDING_APPROVAL, pk__in=held)


def get_visible_event_or_404(user, pk) -> Event:
    return get_object_or_404(visible_events_for_user(user), pk=pk)


def get_visible_event_by_slug_or_404(user, slug) -> Event:
    return get_object_or_404(visible_events_for_user(user), slug=slug)


def find_blocking_upcoming_event(*, venue_id=None, category_id=None) -> bool:
    if not venue_id and not category_id:
        return False

    qs = Event.objects.filter(start_datetime__gt=timezone.now()).exclude(
        status__in=[
            Event.Status.PENDING_APPROVAL,
            Event.Status.REJECTED,
            Event.Status.CANCELLED,
        ]
    )
    if venue_id:
        qs = qs.filter(venue_id=venue_id)
    if category_id:
        qs = qs.filter(category_id=category_id)
    return qs.exists()


def complete_past_events() -> int:
    cutoff = timezone.now() - timedelta(hours=COMPLETE_PAST_EVENTS_BUFFER_HOURS)
    return Event.objects.filter(
        status=Event.Status.APPROVED, end_datetime__lt=cutoff
    ).update(status=Event.Status.COMPLETED, updated_at=timezone.now())
