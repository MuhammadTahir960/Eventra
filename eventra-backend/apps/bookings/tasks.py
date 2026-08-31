from celery import shared_task

from .services import sweep_expired_pending_bookings


@shared_task
def release_expired_bookings():
    sweep_expired_pending_bookings()
