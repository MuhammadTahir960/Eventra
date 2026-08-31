import factory
from factory.django import DjangoModelFactory

from apps.users.factories import UserFactory

from .models import Notification


class NotificationFactory(DjangoModelFactory):
    class Meta:
        model = Notification

    user = factory.SubFactory(UserFactory)
    type = Notification.NotificationType.BOOKING_CONFIRMATION
    status = Notification.Status.SENT
