from datetime import timedelta

from django.db import transaction
from django.db.models import Exists, OuterRef, Q, QuerySet
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


class EventEndNotExtendableError(Exception):
    """Raised when "running late" targets an event that isn't on sale or in review."""


class InvalidEventEndError(Exception):
    """Raised when a "running late" end time is earlier, in the past or too far out."""


PUBLIC_STATUSES = [Event.Status.APPROVED, Event.Status.COMPLETED]
DELETABLE_STATUSES = {Event.Status.CANCELLED, Event.Status.COMPLETED}
SENSITIVE_EVENT_FIELDS = frozenset(
    {"venue", "category", "start_datetime", "end_datetime"}
)
COMPLETE_PAST_EVENTS_BUFFER_HOURS = 2
MAX_RUNNING_LATE_DAYS = 7
RUNNING_LATE_OPENS_HOURS = (
    24
)


def ensure_event_deletable(event: Event) -> None:
    if event.status not in DELETABLE_STATUSES:
        raise EventNotDeletableError(
            "Event must be cancelled or completed before it can be deleted "
            f"(current status: {event.get_status_display()})."
        )
    if (
        event.status == Event.Status.COMPLETED
        and not _has_payout(event)
        and paid_bookings(event).exists()
    ):
        raise EventNotDeletableError(
            "A completed event can't be deleted until its organizer has been paid out."
        )


def _has_payout(event: Event) -> bool:
    return Event.all_objects.filter(pk=event.pk, payout__isnull=False).exists()


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


def lock_event(event: Event) -> None:
    event.refresh_from_db(from_queryset=Event.all_objects.select_for_update())


def approve_event(event: Event) -> Event:
    with transaction.atomic():
        return _approve_locked(event)


def _approve_locked(event: Event) -> Event:
    lock_event(event)
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
    lock_event(event)
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


def cancel_event(event: Event, *, allow_completed: bool = False) -> Event:
    with transaction.atomic():
        return _cancel_locked(event, allow_completed=allow_completed)


def _cancel_locked(event: Event, *, allow_completed: bool = False) -> Event:
    lock_event(event)
    if event.status == Event.Status.COMPLETED:
        if not allow_completed:
            raise EventNotCancellableError(
                "This event has ended. Only an admin can void it."
            )
        if _has_payout(event):
            raise EventNotCancellableError(
                "This event has been paid out, so it can no longer be voided."
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
    public = Q(status__in=PUBLIC_STATUSES, completed_in_review=False)
    if not user or not user.is_authenticated:
        return qs.filter(public)
    if user.role == Roles.ADMIN:
        return qs
    if user.role == Roles.ORGANIZER:
        return qs.filter(Q(organizer=user) | public)
    return qs.filter(public)


def visible_events_for_ticket_holder(user) -> QuerySet:
    qs = visible_events_for_user(user)
    if not user or not user.is_authenticated or user.role == Roles.ADMIN:
        return qs
    held = Booking.objects.filter(user=user, status=Booking.Status.CONFIRMED).values(
        "tickets__event_seat__event"
    )
    hidden = Q(status=Event.Status.PENDING_APPROVAL) | Q(completed_in_review=True)
    return qs | Event.objects.filter(hidden, pk__in=held)


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
    now = timezone.now()
    cutoff = now - timedelta(hours=COMPLETE_PAST_EVENTS_BUFFER_HOURS)
    sold = Booking.objects.filter(
        tickets__event_seat__event=OuterRef("pk"), status=Booking.Status.CONFIRMED
    )
    ended = Event.objects.filter(end_datetime__lt=cutoff)
    completed = ended.filter(status=Event.Status.APPROVED).update(
        status=Event.Status.COMPLETED, completed_at=now, updated_at=now
    )
    return completed + ended.filter(
        Exists(sold), status=Event.Status.PENDING_APPROVAL
    ).update(
        status=Event.Status.COMPLETED,
        completed_at=now,
        completed_in_review=True,
        updated_at=now,
    )


def extend_event_end(event: Event, new_end) -> Event:
    with transaction.atomic():
        lock_event(event)
        if event.status not in (Event.Status.APPROVED, Event.Status.PENDING_APPROVAL):
            raise EventEndNotExtendableError(
                "Only an event that is on sale or in review can run late."
            )
        opens_at = event.start_datetime - timedelta(hours=RUNNING_LATE_OPENS_HOURS)
        if timezone.now() < opens_at:
            raise EventEndNotExtendableError(
                f"Running late opens {RUNNING_LATE_OPENS_HOURS} hours before the start. "
                "To change the time earlier, edit the event; it goes back to review."
            )
        if new_end <= event.end_datetime:
            raise InvalidEventEndError(
                "The new end time must be later than the current one."
            )
        if new_end <= timezone.now():
            raise InvalidEventEndError("The new end time must be in the future.")
        if new_end > event.start_datetime + timedelta(days=MAX_RUNNING_LATE_DAYS):
            raise InvalidEventEndError(
                f"An event can't end more than {MAX_RUNNING_LATE_DAYS} days after it starts."
            )

        moved_day = (
            timezone.localtime(new_end).date()
            != timezone.localtime(event.end_datetime).date()
        )
        event.end_datetime = new_end
        event.save(update_fields=["end_datetime", "updated_at"])
        if moved_day:
            _email_buyers_on_commit(
                "send_event_running_late_email", event, _paid_buyer_ids(event)
            )
    return event
