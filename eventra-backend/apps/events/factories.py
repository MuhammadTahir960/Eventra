from datetime import timedelta
import factory
from django.utils import timezone
from factory.django import DjangoModelFactory
from apps.categories.factories import CategoryFactory
from apps.common.constants import Roles
from apps.users.factories import UserFactory
from apps.venues.factories import VenueFactory
from .models import Event, TicketTier, TierSectionMapping


class EventFactory(DjangoModelFactory):
    class Meta:
        model = Event

    organizer = factory.SubFactory(UserFactory, role=Roles.ORGANIZER)
    venue = factory.SubFactory(VenueFactory)
    category = factory.SubFactory(CategoryFactory)
    title = factory.Sequence(lambda n: f"Event {n}")
    description = "A great event."
    event_type = Event.EventType.GENERAL
    status = Event.Status.APPROVED
    is_seated = True
    is_active = True
    start_datetime = factory.LazyFunction(lambda: timezone.now() + timedelta(days=7))
    end_datetime = factory.LazyFunction(
        lambda: timezone.now() + timedelta(days=7, hours=3)
    )


class TicketTierFactory(DjangoModelFactory):
    class Meta:
        model = TicketTier

    event = factory.SubFactory(EventFactory)
    name = "General Admission"
    price = "25.00"


class TierSectionMappingFactory(DjangoModelFactory):
    class Meta:
        model = TierSectionMapping

    ticket_tier = factory.SubFactory(TicketTierFactory)
    event = factory.LazyAttribute(lambda obj: obj.ticket_tier.event)
    section = "Main"
