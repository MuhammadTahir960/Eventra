import uuid

import factory

from apps.users.factories import UserFactory

from .models import Booking


class BookingFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Booking

    user = factory.SubFactory(UserFactory)
    status = Booking.Status.PENDING
    source_hold_group_id = factory.LazyFunction(uuid.uuid4)
