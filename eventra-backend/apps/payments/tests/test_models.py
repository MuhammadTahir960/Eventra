import pytest
from django.db import IntegrityError, transaction

from ..factories import PaymentFactory
from ..models import Payment

pytestmark = pytest.mark.django_db


def test_booking_payment_relationship_is_unique():
    payment = PaymentFactory()
    with pytest.raises(IntegrityError), transaction.atomic():
        PaymentFactory(booking=payment.booking)


def test_default_status_is_pending():
    payment = PaymentFactory()
    assert payment.status == Payment.Status.PENDING


def test_default_currency_is_usd():
    payment = PaymentFactory()
    assert payment.currency == "usd"
