from celery import shared_task

from apps.bookings.models import Booking

from .services import send_booking_confirmation_email, send_refund_confirmation_email


@shared_task
def send_confirmation_email(booking_id):
    booking = Booking.objects.select_related("user").get(id=booking_id)
    send_booking_confirmation_email(booking)


@shared_task
def send_refund_email(booking_id):
    booking = Booking.objects.select_related("user").get(id=booking_id)
    send_refund_confirmation_email(booking)
