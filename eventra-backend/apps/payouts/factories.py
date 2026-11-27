from decimal import Decimal

import factory
from factory.django import DjangoModelFactory

from apps.events.factories import EventFactory
from apps.events.models import Event
from apps.users.factories import add_payout_account

from .models import OrganizerPayout, Partner


class OrganizerPayoutFactory(DjangoModelFactory):
    class Meta:
        model = OrganizerPayout

    event = factory.SubFactory(EventFactory, status=Event.Status.COMPLETED)
    gross_revenue = Decimal("100.00")
    platform_fee = Decimal("10.00")
    status = OrganizerPayout.Status.PENDING


class PartnerFactory(DjangoModelFactory):
    class Meta:
        model = Partner
        skip_postgeneration_save = True

    name = factory.Sequence(lambda n: f"Partner {n}")

    @factory.post_generation
    def payout_account(partner, create, extracted, **kwargs):
        if create and extracted is not False:
            add_payout_account(partner=partner, holder_name=partner.name)
