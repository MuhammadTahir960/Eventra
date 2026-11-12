from unittest.mock import MagicMock

import pytest
from rest_framework.test import APIClient

from apps.common.constants import Roles
from apps.events.factories import EventFactory, TicketTierFactory
from apps.events.models import Event
from apps.users.factories import UserFactory
from tests.helpers import paid_booking

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
            "data": {
                "object": {
                    "id": "pi_from_webhook",
                    "amount_received": 2500,
                    "currency": "usd",
                }
            },
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
        mock_confirm.assert_called_once_with(
            "pi_from_webhook", amount_received=2500, currency="usd"
        )

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
            "data": {
                "object": {
                    "id": "pi_unknown",
                    "amount_received": 100,
                    "currency": "usd",
                }
            },
        }
        monkeypatch.setattr(
            "apps.payments.views.verify_stripe_webhook_signature",
            MagicMock(return_value=fake_event),
        )

        def _boom(payment_intent_id, **amount):
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


class TestAdminEventPartialRefundsView:
    def _post(self, role, event, percent):
        client = APIClient()
        client.force_authenticate(UserFactory(role=role))
        return client.post(
            f"/admin/events/{event.id}/partial-refunds/",
            {"percent": percent},
            format="json",
        )

    def test_admin_refunds_a_share_once(self, monkeypatch):
        monkeypatch.setattr(
            "apps.payments.services.stripe.Refund.create",
            MagicMock(return_value=MagicMock(id="re_test")),
        )
        event = EventFactory(status=Event.Status.COMPLETED)
        paid_booking(event, (TicketTierFactory(event=event), "40.00"))

        response = self._post(Roles.ADMIN, event, 25)
        assert response.status_code == 201
        assert response.data == {"refunds": 1, "amount": "10.00"}
        assert self._post(Roles.ADMIN, event, 25).status_code == 409

    @pytest.mark.parametrize("percent", [0, 100, "ten"])
    def test_percent_must_be_1_to_99(self, percent):
        event = EventFactory(status=Event.Status.COMPLETED)
        assert self._post(Roles.ADMIN, event, percent).status_code == 400

    def test_organizer_is_forbidden(self):
        event = EventFactory(status=Event.Status.COMPLETED)
        assert self._post(Roles.ORGANIZER, event, 10).status_code == 403
