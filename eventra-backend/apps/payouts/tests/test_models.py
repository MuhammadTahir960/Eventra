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

    def test_payout_reference_is_unique_at_the_database_level(self):
        OrganizerPayoutFactory(payout_reference="PAYOUT-DUPLICATE")

        with pytest.raises(IntegrityError), transaction.atomic():
            OrganizerPayoutFactory(payout_reference="PAYOUT-DUPLICATE")

    def test_event_deletion_is_protected_once_a_payout_exists(self):
        payout = OrganizerPayoutFactory()

        with pytest.raises(ProtectedError):
            payout.event.delete()

    def test_str_includes_reference_and_status(self):
        payout = OrganizerPayoutFactory(
            payout_reference="PAYOUT-STR-TEST", status=OrganizerPayout.Status.SETTLED
        )

        assert str(payout) == "Payout PAYOUT-STR-TEST (settled)"

    def test_no_organizer_id_column_exists_on_the_model(self):
        assert not hasattr(OrganizerPayout, "organizer_id")
