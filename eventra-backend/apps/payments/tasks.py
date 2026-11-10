from celery import shared_task

from apps.bookings.services import cancel_pending_bookings_for_event

from .services import (
    event_ids_with_unrefunded_bookings,
    process_refund,
    refund_event_bookings,
    refund_orphaned_payments,
    retry_event_refunds,
    retry_unfinished_refunds,
)


@shared_task
def refund_event_bookings_task(event_id):
    cancel_pending_bookings_for_event(event_id)
    refund_event_bookings(event_id)


@shared_task
def retry_event_refunds_task(event_id):
    retry_event_refunds(event_id)


@shared_task
def sweep_unrefunded_cancelled_events():
    for event_id in event_ids_with_unrefunded_bookings():
        refund_event_bookings_task.delay(str(event_id))
    refund_orphaned_payments()
    retry_unfinished_refunds()


@shared_task
def process_refund_task(refund_id):
    process_refund(refund_id)
