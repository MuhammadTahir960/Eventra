from decimal import Decimal

import factory
from factory.django import DjangoModelFactory

from apps.events.factories import EventFactory
from apps.events.models import Event

from .models import OrganizerPayout


class OrganizerPayoutFactory(DjangoModelFactory):
    class Meta:
        model = OrganizerPayout

    event = factory.SubFactory(EventFactory, status=Event.Status.COMPLETED)
    gross_revenue = Decimal("100.00")
    platform_fee = Decimal("10.00")
    status = OrganizerPayout.Status.PENDING
