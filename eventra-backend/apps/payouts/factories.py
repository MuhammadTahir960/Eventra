import factory
from factory.django import DjangoModelFactory

from apps.events.factories import EventFactory
from apps.events.models import Event

from .models import OrganizerPayout


class OrganizerPayoutFactory(DjangoModelFactory):
    class Meta:
        model = OrganizerPayout

    event = factory.SubFactory(EventFactory, status=Event.Status.COMPLETED)
    gross_revenue = "100.00"
    platform_fee = "10.00"
    net_amount = "90.00"
    status = OrganizerPayout.Status.PENDING
    payout_reference = factory.LazyAttribute(lambda o: f"PAYOUT-{o.event.id}")
    period_start = factory.LazyAttribute(lambda o: o.event.start_datetime)
    period_end = factory.LazyAttribute(lambda o: o.event.end_datetime)
