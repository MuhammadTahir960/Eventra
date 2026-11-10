import pytest

from apps.bookings.factories import BookingFactory
from apps.payments.factories import PaymentFactory
from apps.payouts.factories import OrganizerPayoutFactory
from apps.tickets.factories import TicketFactory
from apps.users.factories import UserFactory

pytestmark = pytest.mark.django_db

MONEY_RECORDS = [
    ("payments/payment", PaymentFactory, True),
    ("payouts/organizerpayout", OrganizerPayoutFactory, True),
    ("tickets/ticket", TicketFactory, False),
    ("bookings/booking", BookingFactory, False),
]


@pytest.fixture
def superuser_client(client):
    client.force_login(UserFactory(role="admin", is_staff=True, is_superuser=True))
    return client


@pytest.mark.parametrize("path,factory,read_only", MONEY_RECORDS)
def test_superuser_cannot_add_or_delete_money_records(
    superuser_client, path, factory, read_only
):
    record = factory()
    base = f"/django-admin/{path}/"

    assert superuser_client.get(f"{base}add/").status_code == 403
    assert superuser_client.get(f"{base}{record.pk}/delete/").status_code == 403
    assert (
        superuser_client.post(f"{base}{record.pk}/delete/", {"post": "yes"}).status_code
        == 403
    )
    assert type(record)._base_manager.filter(pk=record.pk).exists()
    page = superuser_client.get(f"{base}{record.pk}/change/")
    assert page.status_code == 200
    assert ('name="_save"' in page.content.decode()) is not read_only


@pytest.mark.parametrize("path,factory", [r[:2] for r in MONEY_RECORDS if r[2]])
def test_read_only_records_refuse_a_posted_change(superuser_client, path, factory):
    record = factory()

    response = superuser_client.post(
        f"/django-admin/{path}/{record.pk}/change/", {"status": "failed"}
    )

    assert response.status_code == 403
    record.refresh_from_db()
    assert record.status != "failed"
