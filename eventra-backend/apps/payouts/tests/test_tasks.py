from unittest.mock import MagicMock

import pytest

from apps.events.factories import EventFactory
from apps.events.models import Event

from ..factories import OrganizerPayoutFactory
from ..models import OrganizerPayout
from ..tasks import (
    create_payouts_for_completed_events,
    send_payout_ready_notification,
    send_payout_settled_notification,
    settle_payout,
)

pytestmark = pytest.mark.django_db


class TestCreatePayoutsForCompletedEventsTask:
    def test_delegates_to_the_service_and_returns_its_count(self):
        EventFactory(status=Event.Status.COMPLETED)

        result = create_payouts_for_completed_events()

        assert result == 1
        assert OrganizerPayout.objects.count() == 1


class TestSettlePayoutTask:
    def test_delegates_to_the_service(self, monkeypatch):
        mock_service = MagicMock()
        monkeypatch.setattr("apps.payouts.tasks._settle_payout", mock_service)
        payout = OrganizerPayoutFactory(status=OrganizerPayout.Status.PROCESSING)

        settle_payout(str(payout.id))

        mock_service.assert_called_once_with(str(payout.id))


class TestSendPayoutReadyNotificationTask:
    def test_fetches_the_payout_and_calls_the_notification_service(self, monkeypatch):
        mock_send = MagicMock()
        monkeypatch.setattr("apps.payouts.tasks.send_payout_ready_email", mock_send)
        payout = OrganizerPayoutFactory()

        send_payout_ready_notification(str(payout.id))

        assert mock_send.call_count == 1
        (sent_payout,), _kwargs = mock_send.call_args
        assert sent_payout.id == payout.id


class TestSendPayoutSettledNotificationTask:
    def test_fetches_the_payout_and_calls_the_notification_service(self, monkeypatch):
        mock_send = MagicMock()
        monkeypatch.setattr("apps.payouts.tasks.send_payout_settled_email", mock_send)
        payout = OrganizerPayoutFactory(status=OrganizerPayout.Status.SETTLED)

        send_payout_settled_notification(str(payout.id))

        assert mock_send.call_count == 1
        (sent_payout,), _kwargs = mock_send.call_args
        assert sent_payout.id == payout.id
