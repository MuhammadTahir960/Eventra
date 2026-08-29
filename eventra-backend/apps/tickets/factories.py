import factory
from factory.django import DjangoModelFactory

from apps.bookings.factories import BookingFactory
from apps.seating.factories import EventSeatFactory

from .models import Ticket


class TicketFactory(DjangoModelFactory):
    class Meta:
        model = Ticket

    booking = factory.SubFactory(BookingFactory)
    event_seat = factory.SubFactory(EventSeatFactory)
    status = Ticket.Status.VALID
