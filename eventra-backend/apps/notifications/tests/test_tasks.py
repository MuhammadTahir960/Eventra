import pytest
from django.core import mail

from apps.bookings.factories import BookingFactory

from ..models import Notification
from ..tasks import send_confirmation_email, send_refund_email

pytestmark = pytest.mark.django_db


class TestSendConfirmationEmailTask:
    def test_fetches_booking_and_delegates_to_the_confirmation_service(self):
        booking = BookingFactory()

        send_confirmation_email(str(booking.id))

        assert len(mail.outbox) == 1
        assert mail.outbox[0].to == [booking.user.email]
        assert Notification.objects.filter(
            user=booking.user,
            type=Notification.NotificationType.BOOKING_CONFIRMATION,
        ).exists()


class TestSendRefundEmailTask:
    def test_fetches_booking_and_delegates_to_the_refund_service(self):
        booking = BookingFactory()

        send_refund_email(str(booking.id))

        assert len(mail.outbox) == 1
        assert mail.outbox[0].to == [booking.user.email]
        assert Notification.objects.filter(
            user=booking.user,
            type=Notification.NotificationType.EVENT_CANCELLED_REFUND,
        ).exists()
