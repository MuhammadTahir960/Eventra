from celery import shared_task

from apps.bookings.services import cancel_pending_bookings_for_event

from .services import (
    event_ids_with_unrefunded_bookings,
    refund_event_bookings,
    refund_orphaned_payments,
)


@shared_task
def refund_event_bookings_task(event_id, retry_failed=False):
    cancel_pending_bookings_for_event(event_id)
    refund_event_bookings(event_id, retry_failed=retry_failed)


@shared_task
def sweep_unrefunded_cancelled_events():
    for event_id in event_ids_with_unrefunded_bookings():
        refund_event_bookings_task.delay(str(event_id))
    refund_orphaned_payments()
