import threading
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
import stripe
from django.db import connection

from apps.bookings.factories import BookingFactory
from apps.bookings.models import Booking

from ..models import Payment
from ..services import (
    PaymentGatewayError,
    _to_cents,
    create_or_refresh_payment_intent,
)

pytestmark = pytest.mark.django_db


class TestToCents:
    @pytest.mark.parametrize(
        "dollars,expected_cents",
        [
            (Decimal("9.99"), 999),
            (Decimal("100.00"), 10000),
            (Decimal("0.01"), 1),
            (Decimal("19.995"), 2000),
        ],
    )
    def test_exact_for_representative_values(self, dollars, expected_cents):
        assert _to_cents(dollars) == expected_cents


class TestCreateOrRefreshPaymentIntent:
    def test_creates_payment_with_correct_cents_and_currency(self, monkeypatch):
        booking = BookingFactory(
            status=Booking.Status.PENDING, total_amount=Decimal("49.99")
        )
        fake_intent = MagicMock(id="pi_test_123", client_secret="pi_test_123_secret")
        mock_create = MagicMock(return_value=fake_intent)
        monkeypatch.setattr(
            "apps.payments.services.stripe.PaymentIntent.create", mock_create
        )

        payment = create_or_refresh_payment_intent(booking)

        assert payment.amount == 4999
        assert payment.currency == "usd"
        assert payment.stripe_payment_intent_id == "pi_test_123"
        assert payment.client_secret == "pi_test_123_secret"
        mock_create.assert_called_once()
        _, kwargs = mock_create.call_args
        assert kwargs["idempotency_key"] == booking.idempotency_key
        assert kwargs["metadata"] == {"booking_id": str(booking.id)}

    def test_local_short_circuit_skips_a_second_stripe_call(self, monkeypatch):
        booking = BookingFactory(
            status=Booking.Status.PENDING, total_amount=Decimal("10.00")
        )
        fake_intent = MagicMock(id="pi_test_456", client_secret="pi_test_456_secret")
        mock_create = MagicMock(return_value=fake_intent)
        monkeypatch.setattr(
            "apps.payments.services.stripe.PaymentIntent.create", mock_create
        )

        first = create_or_refresh_payment_intent(booking)
        second = create_or_refresh_payment_intent(booking)

        assert mock_create.call_count == 1
        assert first.id == second.id

    def test_retry_with_existing_payment_row_missing_intent_id_recovers(
        self, monkeypatch
    ):
        booking = BookingFactory(
            status=Booking.Status.PENDING, total_amount=Decimal("12.00")
        )
        Payment.objects.create(
            booking=booking,
            stripe_payment_intent_id="",
            client_secret="",
            amount=1200,
            currency="usd",
            status=Payment.Status.PENDING,
        )
        fake_intent = MagicMock(id="pi_recovered", client_secret="secret_recovered")
        monkeypatch.setattr(
            "apps.payments.services.stripe.PaymentIntent.create",
            MagicMock(return_value=fake_intent),
        )

        payment = create_or_refresh_payment_intent(booking)

        assert payment.stripe_payment_intent_id == "pi_recovered"
        assert payment.client_secret == "secret_recovered"
        assert Payment.objects.filter(booking=booking).count() == 1

    def test_stripe_error_maps_to_payment_gateway_error(self, monkeypatch):
        booking = BookingFactory(
            status=Booking.Status.PENDING, total_amount=Decimal("15.00")
        )

        def _boom(*args, **kwargs):
            raise stripe.error.APIConnectionError("could not connect to Stripe")

        monkeypatch.setattr("apps.payments.services.stripe.PaymentIntent.create", _boom)

        with pytest.raises(PaymentGatewayError):
            create_or_refresh_payment_intent(booking)

        assert Payment.objects.filter(booking=booking).count() == 0

    @pytest.mark.django_db(transaction=True)
    def test_concurrent_calls_without_existing_payment_yield_one_row(self, monkeypatch):
        booking = BookingFactory(
            status=Booking.Status.PENDING, total_amount=Decimal("20.00")
        )
        fake_intent = MagicMock(id="pi_race", client_secret="secret_race")
        monkeypatch.setattr(
            "apps.payments.services.stripe.PaymentIntent.create",
            MagicMock(return_value=fake_intent),
        )

        results = []
        errors = []
        barrier = threading.Barrier(2)

        def attempt():
            barrier.wait()
            try:
                payment = create_or_refresh_payment_intent(booking)
                results.append(payment.id)
            except Exception as exc:
                errors.append(exc)
            finally:
                connection.close()

        threads = [threading.Thread(target=attempt) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
        assert Payment.objects.filter(booking=booking).count() == 1
        assert len(results) == 2
        assert len(set(results)) == 1
