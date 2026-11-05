from celery import shared_task

from apps.bookings.models import Booking
from apps.events.models import Event
from apps.payments.models import Refund
from apps.users.models import User

from .services import (
    send_booking_confirmation_email,
    send_event_cancelled_notice,
    send_event_postponed_notice,
    send_event_reminders_batch,
    send_event_running_late_notice,
    send_event_updated_notice,
    send_refund_notice,
)

_RETRY = {"autoretry_for": (Exception,), "retry_backoff": True, "max_retries": 3}


@shared_task(**_RETRY)
def send_confirmation_email(booking_id):
    booking = Booking.objects.select_related("user").get(id=booking_id)
    send_booking_confirmation_email(booking)


@shared_task(**_RETRY)
def send_refund_email(refund_id):
    send_refund_notice(Refund.objects.select_related("booking__user").get(id=refund_id))


@shared_task(**_RETRY)
def send_event_postponed_email(event_id, user_id):
    user = User.objects.filter(id=user_id, is_active=True).first()
    if user is not None:
        event = Event.all_objects.select_related("venue").get(id=event_id)
        send_event_postponed_notice(event, user)


@shared_task(**_RETRY)
def send_event_updated_email(event_id, user_id):
    user = User.objects.filter(id=user_id, is_active=True).first()
    if user is not None:
        event = Event.all_objects.select_related("venue").get(id=event_id)
        send_event_updated_notice(event, user)


@shared_task(**_RETRY)
def send_event_running_late_email(event_id, user_id):
    user = User.objects.filter(id=user_id, is_active=True).first()
    if user is not None:
        event = Event.all_objects.select_related("venue").get(id=event_id)
        send_event_running_late_notice(event, user)


@shared_task(**_RETRY)
def send_event_cancelled_email(event_id, user_id):
    user = User.objects.filter(id=user_id, is_active=True).first()
    if user is not None:
        send_event_cancelled_notice(Event.all_objects.get(id=event_id), user)


@shared_task
def send_event_reminders():
    send_event_reminders_batch()
