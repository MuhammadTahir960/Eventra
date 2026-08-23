import pytest
from django.contrib.admin.sites import AdminSite

from apps.bookings.factories import BookingFactory

from ..admin import PaymentAdmin
from ..models import Payment

pytestmark = pytest.mark.django_db


def test_stripe_identity_fields_are_not_editable_in_admin_form():
    payment = Payment.objects.create(
        booking=BookingFactory(),
        stripe_payment_intent_id="pi_test123",
        client_secret="pi_test123_secret_abc",
        amount=1999,
        currency="usd",
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
        amount=500,
        currency="usd",
        status=Payment.Status.SUCCEEDED,
    )

    admin = PaymentAdmin(Payment, AdminSite())
    all_fields = admin.get_fields(request=None, obj=payment)

    assert "client_secret" in all_fields
    assert "stripe_payment_intent_id" in all_fields
