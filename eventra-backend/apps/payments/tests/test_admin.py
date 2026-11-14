import pytest
from django.contrib.admin.sites import AdminSite

from apps.bookings.factories import BookingFactory
from apps.events.factories import EventFactory, TicketTierFactory
from apps.seating.factories import EventSeatFactory
from apps.tickets.factories import TicketFactory
from apps.tickets.models import Ticket
from tests.helpers import failed_refund, paid_booking

from ..admin import PaymentAdmin, RefundAdmin
from ..models import Payment, Refund

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


def test_refunds_list_shows_the_event_and_the_refund_total():
    event = EventFactory()
    tier = TicketTierFactory(event=event)
    failed_refund(paid_booking(event, (tier, "20.00"), (tier, "15.50")))

    admin = RefundAdmin(Refund, AdminSite())
    refund = admin.get_queryset(request=None).get()

    assert admin.event(refund) == event.title
    assert str(admin.amount(refund)) == "35.50"


def test_refunds_are_read_only_records():
    admin = RefundAdmin(Refund, AdminSite())
    assert not admin.has_add_permission(request=None)
    assert not admin.has_change_permission(request=None)
    assert not admin.has_delete_permission(request=None)
