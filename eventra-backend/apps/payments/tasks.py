from celery import shared_task

from .services import refund_event_bookings


@shared_task
def refund_event_bookings_task(event_id, only_failed=False):
    refund_event_bookings(event_id, only_failed=only_failed)
