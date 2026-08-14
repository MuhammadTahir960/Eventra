from datetime import timedelta

import pytest
from django.utils import timezone

from ..factories import EventFactory
from ..models import Event
from ..tasks import complete_past_events

pytestmark = pytest.mark.django_db


def test_task_delegates_to_service_and_completes_past_event():
    end = timezone.now() - timedelta(hours=3)
    event = EventFactory(
        status=Event.Status.APPROVED,
        start_datetime=end - timedelta(hours=3),
        end_datetime=end,
    )

    result = complete_past_events()

    event.refresh_from_db()
    assert result == 1
    assert event.status == Event.Status.COMPLETED
