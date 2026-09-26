from celery import shared_task

from apps.bookings.models import Booking

from .services import (
    send_booking_confirmation_email,
    send_event_reminders_batch,
    send_refund_confirmation_email,
)

_RETRY = {"autoretry_for": (Exception,), "retry_backoff": True, "max_retries": 3}


@shared_task(**_RETRY)
def send_confirmation_email(booking_id):
    booking = Booking.objects.select_related("user").get(id=booking_id)
    send_booking_confirmation_email(booking)


@shared_task(**_RETRY)
def send_refund_email(booking_id, event_cancelled=True):
    booking = Booking.objects.select_related("user").get(id=booking_id)
    send_refund_confirmation_email(booking, event_cancelled=event_cancelled)


@shared_task
def send_event_reminders():
    send_event_reminders_batch()
