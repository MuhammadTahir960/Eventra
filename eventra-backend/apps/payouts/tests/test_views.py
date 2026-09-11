from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from django.urls import resolve
from rest_framework import status
from rest_framework.test import APIClient

from apps.bookings.factories import BookingFactory
from apps.bookings.models import Booking
from apps.common.constants import Roles
from apps.events.factories import EventFactory
from apps.events.models import Event
from apps.seating.factories import EventSeatFactory
from apps.seating.models import EventSeat
from apps.tickets.models import Ticket
from apps.users.factories import UserFactory

from ..factories import OrganizerPayoutFactory
from ..models import OrganizerPayout
from ..views import (
    AdminPayoutListView,
    AdminPayoutSettleView,
    OrganizerEventSalesView,
    OrganizerPayoutListView,
)

pytestmark = pytest.mark.django_db


def _authed_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _confirmed_booking_with_ticket(event, total_amount):
    booking = BookingFactory(status=Booking.Status.CONFIRMED, total_amount=total_amount)
    seat = EventSeatFactory(
        event=event, status=EventSeat.Status.BOOKED, price_override=total_amount
    )
    Ticket.objects.create(booking=booking, event_seat=seat, status=Ticket.Status.VALID)
    return booking


class TestUrlsResolveToDedicatedViews:
    def test_admin_payout_list_route(self):
        assert resolve("/admin/payouts/").func.cls == AdminPayoutListView

    def test_admin_payout_settle_route(self):
        payout = OrganizerPayoutFactory()
        match = resolve(f"/admin/payouts/{payout.id}/settle/")
        assert match.func.cls == AdminPayoutSettleView

    def test_organizer_payout_list_route(self):
        assert resolve("/organizer/payouts/").func.cls == OrganizerPayoutListView

    def test_organizer_event_sales_route(self):
        event = EventFactory()
        match = resolve(f"/organizer/events/{event.id}/sales/")
        assert match.func.cls == OrganizerEventSalesView


class TestOrganizerEventSalesView:
    def test_owning_organizer_sees_sales(self):
        organizer = UserFactory(role=Roles.ORGANIZER)
        event = EventFactory(organizer=organizer, status=Event.Status.COMPLETED)
        _confirmed_booking_with_ticket(event, Decimal("40.00"))

        response = _authed_client(organizer).get(f"/organizer/events/{event.id}/sales/")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["tickets_sold"] == 1
        assert Decimal(response.data["gross_revenue"]) == Decimal("40.00")
        assert len(response.data["tickets"]) == 1
        assert response.data["tickets"][0]["status"] == "confirmed"

    def test_refunded_ticket_is_reflected_over_http(self):
        organizer = UserFactory(role=Roles.ORGANIZER)
        event = EventFactory(organizer=organizer, status=Event.Status.COMPLETED)
        booking = _confirmed_booking_with_ticket(event, Decimal("60.00"))
        booking.status = Booking.Status.REFUNDED
        booking.save(update_fields=["status"])

        response = _authed_client(organizer).get(f"/organizer/events/{event.id}/sales/")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["tickets_sold"] == 1
        assert Decimal(response.data["gross_revenue"]) == Decimal("0.00")
        assert response.data["tickets"][0]["status"] == "refunded"
        assert Decimal(response.data["tickets"][0]["amount"]) == Decimal("60.00")

    def test_event_with_no_sales_returns_zeroed_response(self):
        organizer = UserFactory(role=Roles.ORGANIZER)
        event = EventFactory(organizer=organizer, status=Event.Status.COMPLETED)

        response = _authed_client(organizer).get(f"/organizer/events/{event.id}/sales/")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["tickets_sold"] == 0
        assert Decimal(response.data["gross_revenue"]) == Decimal("0.00")
        assert response.data["tickets"] == []

    def test_owning_organizer_can_still_see_sales_for_a_soft_deleted_event(self):
        organizer = UserFactory(role=Roles.ORGANIZER)
        event = EventFactory(
            organizer=organizer, status=Event.Status.COMPLETED, is_active=False
        )
        _confirmed_booking_with_ticket(event, Decimal("20.00"))

        response = _authed_client(organizer).get(f"/organizer/events/{event.id}/sales/")

        assert response.status_code == status.HTTP_200_OK
        assert Decimal(response.data["gross_revenue"]) == Decimal("20.00")

    def test_nonexistent_event_returns_404(self):
        organizer = UserFactory(role=Roles.ORGANIZER)
        missing_id = "11111111-1111-1111-1111-111111111111"

        response = _authed_client(organizer).get(
            f"/organizer/events/{missing_id}/sales/"
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_malformed_event_id_returns_404_not_500(self):
        organizer = UserFactory(role=Roles.ORGANIZER)

        response = _authed_client(organizer).get(
            "/organizer/events/not-a-real-uuid/sales/"
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_non_owning_organizer_is_rejected(self):
        event = EventFactory()
        other_organizer = UserFactory(role=Roles.ORGANIZER)

        response = _authed_client(other_organizer).get(
            f"/organizer/events/{event.id}/sales/"
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_admin_is_not_granted_access(self):
        event = EventFactory()
        admin = UserFactory(role=Roles.ADMIN)

        response = _authed_client(admin).get(f"/organizer/events/{event.id}/sales/")

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_unauthenticated_is_rejected(self):
        event = EventFactory()

        response = APIClient().get(f"/organizer/events/{event.id}/sales/")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestOrganizerPayoutListView:
    def test_only_lists_own_events_payouts(self):
        organizer = UserFactory(role=Roles.ORGANIZER)
        own_event = EventFactory(organizer=organizer, status=Event.Status.COMPLETED)
        own_payout = OrganizerPayoutFactory(event=own_event)
        OrganizerPayoutFactory()

        response = _authed_client(organizer).get("/organizer/payouts/")

        assert response.status_code == status.HTTP_200_OK
        returned_ids = {row["id"] for row in response.data["results"]}
        assert returned_ids == {str(own_payout.id)}

    def test_attendee_is_rejected(self):
        response = _authed_client(UserFactory(role=Roles.ATTENDEE)).get(
            "/organizer/payouts/"
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN


class TestAdminPayoutListView:
    def test_admin_sees_all_payouts(self):
        OrganizerPayoutFactory()
        OrganizerPayoutFactory()
        admin = UserFactory(role=Roles.ADMIN)

        response = _authed_client(admin).get("/admin/payouts/")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 2

    def test_filters_by_status(self):
        OrganizerPayoutFactory(status=OrganizerPayout.Status.PENDING)
        settled = OrganizerPayoutFactory(status=OrganizerPayout.Status.SETTLED)
        admin = UserFactory(role=Roles.ADMIN)

        response = _authed_client(admin).get("/admin/payouts/?status=settled")

        assert response.status_code == status.HTTP_200_OK
        returned_ids = {row["id"] for row in response.data["results"]}
        assert returned_ids == {str(settled.id)}

    def test_non_admin_is_rejected(self):
        organizer = UserFactory(role=Roles.ORGANIZER)

        response = _authed_client(organizer).get("/admin/payouts/")

        assert response.status_code == status.HTTP_403_FORBIDDEN


class TestAdminPayoutSettleView:
    def test_admin_settle_returns_202_and_flips_to_processing(
        self, monkeypatch, django_capture_on_commit_callbacks
    ):
        monkeypatch.setattr("apps.payouts.tasks.settle_payout", MagicMock())
        payout = OrganizerPayoutFactory(status=OrganizerPayout.Status.PENDING)
        admin = UserFactory(role=Roles.ADMIN)

        with django_capture_on_commit_callbacks(execute=True):
            response = _authed_client(admin).post(f"/admin/payouts/{payout.id}/settle/")

        assert response.status_code == status.HTTP_202_ACCEPTED
        assert response.data["status"] == OrganizerPayout.Status.PROCESSING
        payout.refresh_from_db()
        assert payout.status == OrganizerPayout.Status.PROCESSING

    def test_already_settled_returns_409(self):
        payout = OrganizerPayoutFactory(status=OrganizerPayout.Status.SETTLED)
        admin = UserFactory(role=Roles.ADMIN)

        response = _authed_client(admin).post(f"/admin/payouts/{payout.id}/settle/")

        assert response.status_code == status.HTTP_409_CONFLICT

    def test_non_admin_is_rejected(self):
        payout = OrganizerPayoutFactory()
        organizer = UserFactory(role=Roles.ORGANIZER)

        response = _authed_client(organizer).post(f"/admin/payouts/{payout.id}/settle/")

        assert response.status_code == status.HTTP_403_FORBIDDEN
