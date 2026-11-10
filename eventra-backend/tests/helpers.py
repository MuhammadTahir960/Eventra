from decimal import Decimal
from types import SimpleNamespace

from django.contrib.auth.models import AnonymousUser
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.bookings.factories import BookingFactory
from apps.bookings.models import Booking
from apps.payments.factories import PaymentFactory
from apps.payments.models import Payment, Refund
from apps.seating.factories import EventSeatFactory
from apps.seating.models import EventSeat
from apps.tickets.factories import TicketFactory
from apps.tickets.models import Ticket
from apps.users.factories import UserFactory


def results(response):
    return (
        response.data.get("results", response.data)
        if isinstance(response.data, dict)
        else response.data
    )


def paid_booking(event, *seats_and_prices, user=None):
    booking = BookingFactory(
        user=user or UserFactory(), status=Booking.Status.CONFIRMED
    )
    for tier, price in seats_and_prices:
        seat = EventSeatFactory(
            event=event, ticket_tier=tier, status=EventSeat.Status.BOOKED
        )
        TicketFactory(booking=booking, event_seat=seat, price=Decimal(price))
    PaymentFactory(
        booking=booking,
        stripe_payment_intent_id=f"pi_{booking.id}",
        status=Payment.Status.SUCCEEDED,
    )
    return booking


def confirmed_booking_with_ticket(event, total_amount):
    booking = BookingFactory(status=Booking.Status.CONFIRMED)
    seat = EventSeatFactory(
        event=event, status=EventSeat.Status.BOOKED, price_override=total_amount
    )
    TicketFactory(booking=booking, event_seat=seat, status=Ticket.Status.VALID)
    return booking


def unpaid_booking(price="49.99", *, event=None, **booking_fields):
    booking = BookingFactory(status=Booking.Status.PENDING, **booking_fields)
    seat_fields = {"event": event} if event is not None else {}
    seat = EventSeatFactory(status=EventSeat.Status.HELD, **seat_fields)
    TicketFactory(
        booking=booking,
        event_seat=seat,
        price=Decimal(price),
        status=Ticket.Status.PENDING,
    )
    return booking


def auth_client(user):
    client = APIClient()
    client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}"
    )
    return client


def fake_request(user=None, method="GET"):
    return SimpleNamespace(user=user or AnonymousUser(), method=method)


def user_with_role(role):
    return UserFactory(role=role) if role else AnonymousUser()


def failed_refund(booking, reason=Refund.Reason.CANCELLED_EVENT):
    refund = Refund.objects.create(
        booking=booking,
        reason=reason,
        status=Refund.Status.FAILED,
        key=f"failed-{booking.id}",
    )
    for ticket in booking.tickets.all():
        refund.items.create(ticket=ticket, amount=ticket.price)
    return refund
