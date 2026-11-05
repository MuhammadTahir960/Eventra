import pytest
from django.contrib.admin.sites import AdminSite

from apps.bookings.factories import BookingFactory
from apps.seating.factories import EventSeatFactory
from apps.tickets.factories import TicketFactory
from apps.tickets.models import Ticket

from ..admin import PaymentAdmin
from ..models import Payment

pytestmark = pytest.mark.django_db


def test_stripe_identity_fields_are_not_editable_in_admin_form():
    payment = Payment.objects.create(
        booking=BookingFactory(),
        stripe_payment_intent_id="pi_test123",
        client_secret="pi_test123_secret_abc",
        status=Payment.Status.PENDING,
    )

    admin = PaymentAdmin(Payment, AdminSite())
    readonly = admin.get_readonly_fields(request=None, obj=payment)

    assert "client_secret" in readonly
    assert "stripe_payment_intent_id" in readonly


def test_stripe_identity_fields_still_visible_for_support_debugging():
    payment = Payment.objects.create(
        booking=BookingFactory(),
        stripe_payment_intent_id="pi_test456",
        client_secret="pi_test456_secret_xyz",
        status=Payment.Status.SUCCEEDED,
    )

    admin = PaymentAdmin(Payment, AdminSite())
    all_fields = admin.get_fields(request=None, obj=payment)

    assert "client_secret" in all_fields
    assert "stripe_payment_intent_id" in all_fields


def test_payments_list_names_the_event_of_an_orphaned_payment():
    booking = BookingFactory(status="cancelled")
    seat = EventSeatFactory()
    TicketFactory(booking=booking, event_seat=seat, status=Ticket.Status.CANCELLED)
    Payment.objects.create(
        booking=booking,
        stripe_payment_intent_id="pi_orphan",
        client_secret="pi_orphan_secret",
        status=Payment.Status.SUCCEEDED,
    )

    admin = PaymentAdmin(Payment, AdminSite())
    payment = admin.get_queryset(request=None).get()

    assert admin.event(payment) == seat.event.title
