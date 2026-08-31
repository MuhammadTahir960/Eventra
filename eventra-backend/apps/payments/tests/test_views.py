from unittest.mock import MagicMock

import pytest
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db


class TestStripeWebhookView:
    def test_invalid_signature_returns_400_and_does_not_confirm(self, monkeypatch):
        from ..services import WebhookSignatureError

        def _boom(*args, **kwargs):
            raise WebhookSignatureError("bad signature")

        monkeypatch.setattr(
            "apps.payments.views.verify_stripe_webhook_signature", _boom
        )
        mock_confirm = MagicMock()
        monkeypatch.setattr(
            "apps.payments.views.confirm_payment_from_webhook", mock_confirm
        )

        client = APIClient()
        response = client.post(
            "/webhooks/stripe/",
            data=b"{}",
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="bad",
        )

        assert response.status_code == 400
        mock_confirm.assert_not_called()

    def test_valid_payment_intent_succeeded_confirms_payment(self, monkeypatch):
        fake_event = {
            "type": "payment_intent.succeeded",
            "data": {"object": {"id": "pi_from_webhook"}},
        }
        monkeypatch.setattr(
            "apps.payments.views.verify_stripe_webhook_signature",
            MagicMock(return_value=fake_event),
        )
        mock_confirm = MagicMock()
        monkeypatch.setattr(
            "apps.payments.views.confirm_payment_from_webhook", mock_confirm
        )

        client = APIClient()
        response = client.post(
            "/webhooks/stripe/",
            data=b"{}",
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="valid",
        )

        assert response.status_code == 200
        mock_confirm.assert_called_once_with("pi_from_webhook")

    def test_unhandled_event_type_returns_200_without_acting(self, monkeypatch):
        fake_event = {"type": "charge.refunded", "data": {"object": {}}}
        monkeypatch.setattr(
            "apps.payments.views.verify_stripe_webhook_signature",
            MagicMock(return_value=fake_event),
        )
        mock_confirm = MagicMock()
        monkeypatch.setattr(
            "apps.payments.views.confirm_payment_from_webhook", mock_confirm
        )

        client = APIClient()
        response = client.post(
            "/webhooks/stripe/",
            data=b"{}",
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="valid",
        )

        assert response.status_code == 200
        mock_confirm.assert_not_called()

    def test_unknown_payment_intent_still_returns_200(self, monkeypatch):
        from ..services import PaymentNotFoundError

        fake_event = {
            "type": "payment_intent.succeeded",
            "data": {"object": {"id": "pi_unknown"}},
        }
        monkeypatch.setattr(
            "apps.payments.views.verify_stripe_webhook_signature",
            MagicMock(return_value=fake_event),
        )

        def _boom(payment_intent_id):
            raise PaymentNotFoundError(payment_intent_id)

        monkeypatch.setattr("apps.payments.views.confirm_payment_from_webhook", _boom)

        client = APIClient()
        response = client.post(
            "/webhooks/stripe/",
            data=b"{}",
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="valid",
        )

        assert response.status_code == 200

    def test_no_authentication_required(self, monkeypatch):
        """AllowAny is explicit -- Stripe has no JWT to send."""
        monkeypatch.setattr(
            "apps.payments.views.verify_stripe_webhook_signature",
            MagicMock(return_value={"type": "unhandled.type", "data": {"object": {}}}),
        )
        client = APIClient()
        response = client.post(
            "/webhooks/stripe/",
            data=b"{}",
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="valid",
        )
        assert response.status_code == 200
