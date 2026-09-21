from celery import shared_task

from apps.bookings.services import cancel_pending_bookings_for_event

from .services import refund_event_bookings


@shared_task
def refund_event_bookings_task(event_id, only_failed=False):
    cancel_pending_bookings_for_event(event_id)
    refund_event_bookings(event_id, only_failed=only_failed)
