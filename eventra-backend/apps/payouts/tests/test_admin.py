import pytest
from django.test import Client

from apps.common.constants import Roles
from apps.users.factories import UserFactory

from .. import account_numbers
from ..factories import PartnerFactory
from ..models import Partner, PayoutAccount

pytestmark = pytest.mark.django_db


def _client():
    client = Client()
    client.force_login(UserFactory(role=Roles.ADMIN, is_staff=True, is_superuser=True))
    return client


def _payout_fields(token):
    return {
        "method": "bank",
        "provider": "Riverside Savings Bank",
        "holder_name": "Riverside Football Association",
        "number_token": token,
    }


class TestPartnerAdmin:
    url = "/django-admin/payouts/partner/add/"

    def test_the_add_page_shows_a_locked_generated_number(self):
        page = _client().get(self.url).content.decode()

        assert 'name="account_number_display"' in page
        assert "disabled" in page.split('name="account_number_display"')[1][:200]

    def test_adding_a_partner_creates_it_with_the_shown_number(self):
        issued = account_numbers.issue()

        response = _client().post(
            self.url,
            {
                "name": "Riverside FA",
                "is_active": "on",
                **_payout_fields(issued["token"]),
            },
        )

        assert response.status_code == 302
        account = PayoutAccount.objects.get(partner__name="Riverside FA")
        assert account_numbers.decrypt(account.account_number) == issued["number"]

    def test_a_tampered_token_creates_neither_partner_nor_account(self):
        token = account_numbers.issue()["token"]
        tampered = token[:-1] + ("A" if token[-1] != "A" else "B")

        response = _client().post(
            self.url, {"name": "Riverside FA", **_payout_fields(tampered)}
        )

        assert response.status_code == 200
        assert not Partner.objects.filter(name="Riverside FA").exists()


class TestPayoutAccountAdmin:
    def test_adding_an_organizer_account_saves_the_shown_number(self):
        organizer = UserFactory(role=Roles.ORGANIZER, payout_account=False)
        issued = account_numbers.issue()

        response = _client().post(
            "/django-admin/payouts/payoutaccount/add/",
            {"organizer": organizer.id, **_payout_fields(issued["token"])},
        )

        assert response.status_code == 302
        assert (
            account_numbers.decrypt(organizer.payout_account.account_number)
            == issued["number"]
        )

    def test_the_change_page_never_shows_the_full_number(self):
        account = PartnerFactory().payout_account
        number = account_numbers.decrypt(account.account_number)

        response = _client().get(
            f"/django-admin/payouts/payoutaccount/{account.id}/change/"
        )

        assert response.status_code == 200
        assert f"•••• {number[-4:]}" in response.content.decode()
        assert number not in response.content.decode()
