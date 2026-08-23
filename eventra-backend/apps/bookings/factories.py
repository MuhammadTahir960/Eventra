import uuid
from decimal import Decimal

import factory

from apps.users.factories import UserFactory

from .models import Booking


class BookingFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Booking

    user = factory.SubFactory(UserFactory)
    status = Booking.Status.PENDING
    total_amount = Decimal("49.99")
    source_hold_group_id = factory.LazyFunction(uuid.uuid4)
    idempotency_key = factory.LazyFunction(lambda: str(uuid.uuid4()))
