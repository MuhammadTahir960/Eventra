import os
import subprocess
import sys
import threading
from decimal import Decimal
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from django.contrib.auth.models import AnonymousUser
from django.db import connection
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.bookings.factories import BookingFactory
from apps.bookings.models import Booking
from apps.payments.factories import PaymentFactory
from apps.payments.models import Payment, Refund
from apps.payments.services import _to_cents, confirm_payment_from_webhook
from apps.seating.factories import EventSeatFactory
from apps.seating.models import EventSeat
from apps.tickets.factories import TicketFactory
from apps.tickets.models import Ticket
from apps.users.factories import UserFactory


def wall_clock(moment, time_zone="America/Guayaquil"):
    return moment.astimezone(ZoneInfo(time_zone)).strftime("%Y-%m-%dT%H:%M:%S")


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


def confirm_paid_in_full(payment_intent_id):
    payment = (
        Payment.objects.filter(stripe_payment_intent_id=payment_intent_id)
        .select_related("booking")
        .first()
    )
    cents = _to_cents(payment.booking.total_amount) if payment else 0
    return confirm_payment_from_webhook(
        payment_intent_id,
        amount_received=cents,
        currency=payment.booking.event.currency if payment else "",
    )


def race(*calls, timeout=15):
    barrier = threading.Barrier(len(calls))
    outcomes = [None] * len(calls)

    def run(index, call):
        barrier.wait()
        try:
            outcomes[index] = call()
        except Exception as exc:  # noqa: BLE001
            outcomes[index] = exc
        finally:
            connection.close()

    threads = [threading.Thread(target=run, args=pair) for pair in enumerate(calls)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout)
    assert not any(thread.is_alive() for thread in threads), "a racing call hung"
    return outcomes


PROD_ENV = {
    "SECRET_KEY": "test-only-" + "k3y-" * 12,
    "JWT_SIGNING_KEY": "test-only-" + "jwt-" * 12,
    "ALLOWED_HOSTS": "example.com",
    "CSRF_TRUSTED_ORIGINS": "https://example.com",
    "CORS_ALLOWED_ORIGINS": "https://example.com",
    "EMAIL_HOST": "smtp.example.com",
    "DEFAULT_FROM_EMAIL": "Eventra <hello@example.com>",
    "EMAIL_REPLY_TO": "help@example.com",
    "FRONTEND_URL": "https://example.com",
    "TURNSTILE_SECRET_KEY": "0x4AAAAAAAreal-looking-secret",
    "R2_ACCOUNT_ID": "demo-account-id",
    "R2_ACCESS_KEY_ID": "demo-access-key",
    "R2_SECRET_ACCESS_KEY": "demo-secret-key",
    "R2_BUCKET_NAME": "demo-bucket",
    "R2_PUBLIC_DOMAIN": "media.example.com",
}


def run_with_settings(settings_module, env=None, code="import django; django.setup()"):
    return subprocess.run(
        [sys.executable, "-c", code],
        env={**os.environ, "DJANGO_SETTINGS_MODULE": settings_module, **(env or {})},
        capture_output=True,
        text=True,
        timeout=60,
    )
