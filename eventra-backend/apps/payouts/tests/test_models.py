from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError

from apps.events.factories import EventFactory
from apps.events.models import Event

from ..factories import OrganizerPayoutFactory
from ..models import OrganizerPayout

pytestmark = pytest.mark.django_db


class TestOrganizerPayoutModel:
    def test_event_id_is_unique_at_the_database_level(self):
        event = EventFactory(status=Event.Status.COMPLETED)
        OrganizerPayoutFactory(event=event)

        with pytest.raises(IntegrityError), transaction.atomic():
            OrganizerPayoutFactory(event=event)

    def test_event_deletion_is_protected_once_a_payout_exists(self):
        payout = OrganizerPayoutFactory()

        with pytest.raises(ProtectedError):
            payout.event.delete()

    def test_str_names_the_event_and_status(self):
        payout = OrganizerPayoutFactory(status=OrganizerPayout.Status.SETTLED)

        assert str(payout) == f"Payout for {payout.event_id} (settled)"

    def test_net_amount_is_sales_less_the_platform_fee(self):
        payout = OrganizerPayoutFactory(
            gross_revenue=Decimal("120.00"), platform_fee=Decimal("12.00")
        )

        assert payout.net_amount == Decimal("108.00")

    def test_no_organizer_id_column_exists_on_the_model(self):
        assert not hasattr(OrganizerPayout, "organizer_id")
