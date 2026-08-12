from datetime import timedelta
import factory
from django.utils import timezone
from factory.django import DjangoModelFactory
from apps.events.factories import EventFactory, TicketTierFactory
from apps.users.factories import UserFactory
from apps.venues.factories import SeatFactory
from .models import EventSeat, SeatHold


class EventSeatFactory(DjangoModelFactory):
    class Meta:
        model = EventSeat

    event = factory.SubFactory(EventFactory)
    seat = factory.SubFactory(SeatFactory)
    ticket_tier = factory.SubFactory(TicketTierFactory)
    status = EventSeat.Status.AVAILABLE


class SeatHoldFactory(DjangoModelFactory):
    class Meta:
        model = SeatHold

    group_id = factory.Faker("uuid4")
    event_seat = factory.SubFactory(EventSeatFactory)
    user = factory.SubFactory(UserFactory)
    expires_at = factory.LazyFunction(lambda: timezone.now() + timedelta(minutes=10))
