import factory
from factory.django import DjangoModelFactory
from apps.venues.models import Venue, Seat


class VenueFactory(DjangoModelFactory):
    class Meta:
        model = Venue

    name = factory.Sequence(lambda n: f"Venue {n}")
    address = factory.Faker("street_address")
    city = "Nairobi"
    country = "Kenya"
    capacity = 100
    is_active = True


class SeatFactory(DjangoModelFactory):
    class Meta:
        model = Seat

    venue = factory.SubFactory(VenueFactory)
    section = "Main"
    row_label = "A"
    seat_number = factory.Sequence(lambda n: n + 1)
