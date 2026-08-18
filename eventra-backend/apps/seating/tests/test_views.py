import threading
import uuid

import pytest
from django.db import connection
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.events.factories import (
    EventFactory,
    TicketTierFactory,
    TierSectionMappingFactory,
)
from apps.events.models import Event
from apps.users.factories import UserFactory
from apps.venues.factories import SeatFactory

from ..factories import EventSeatFactory
from ..models import EventSeat
from ..services import MAX_SEATS_PER_HOLD

pytestmark = pytest.mark.django_db


def auth_client(user):
    client = APIClient()
    access = RefreshToken.for_user(user).access_token
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return client


def _seated_approved_event(organizer=None, section="Main"):
    kwargs = {"is_seated": True, "status": Event.Status.APPROVED}
    if organizer is not None:
        kwargs["organizer"] = organizer
    event = EventFactory(**kwargs)
    SeatFactory(venue=event.venue, section=section, row_label="A", seat_number=1)
    SeatFactory(venue=event.venue, section=section, row_label="A", seat_number=2)
    tier = TicketTierFactory(event=event)
    TierSectionMappingFactory(event=event, ticket_tier=tier, section=section)
    return event


# ==================================================
# GET /events/{id}/seats/
# ==================================================


class TestGetSeats:
    def test_anonymous_can_view_seat_map_of_approved_event(self, api_client):
        event = EventFactory(status=Event.Status.APPROVED)
        seat = EventSeatFactory(event=event)

        response = api_client.get(f"/events/{event.id}/seats/")
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1
        assert response.data[0]["id"] == str(seat.id)

    def test_seat_map_never_exposes_who_holds_a_seat(self, api_client):
        event = EventFactory(status=Event.Status.APPROVED)
        EventSeatFactory(event=event, status=EventSeat.Status.HELD)

        response = api_client.get(f"/events/{event.id}/seats/")
        assert response.status_code == status.HTTP_200_OK
        assert "user_id" not in response.data[0]
        assert "user" not in response.data[0]
        assert response.data[0]["status"] == "held"

    def test_pending_event_seat_map_hidden_from_anonymous(self, api_client):
        event = EventFactory(status=Event.Status.PENDING_APPROVAL)
        response = api_client.get(f"/events/{event.id}/seats/")
        assert response.status_code == status.HTTP_404_NOT_FOUND


# ==================================================
# POST /events/{id}/seats/instantiate/
# ==================================================


class TestInstantiateSeats:
    def test_owner_organizer_can_instantiate(self, organizer_user):
        event = _seated_approved_event(organizer=organizer_user)
        client = auth_client(organizer_user)

        response = client.post(f"/events/{event.id}/seats/instantiate/")
        assert response.status_code == status.HTTP_201_CREATED
        assert len(response.data) == 2
        assert EventSeat.objects.filter(event=event).count() == 2

    def test_other_organizer_cannot_instantiate(self, organizer_user):
        owner = UserFactory(role="organizer")
        event = _seated_approved_event(organizer=owner)
        client = auth_client(organizer_user)

        response = client.post(f"/events/{event.id}/seats/instantiate/")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_admin_cannot_instantiate_organizer_owned_event(self, admin_user):
        """Strict-owner semantics, same as PATCH and ticket-tiers — no admin override."""
        owner = UserFactory(role="organizer")
        event = _seated_approved_event(organizer=owner)
        client = auth_client(admin_user)

        response = client.post(f"/events/{event.id}/seats/instantiate/")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_unauthenticated_cannot_instantiate(self, api_client):
        event = _seated_approved_event()
        response = api_client.post(f"/events/{event.id}/seats/instantiate/")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_non_seated_event_returns_400(self, organizer_user):
        event = EventFactory(organizer=organizer_user, is_seated=False)
        client = auth_client(organizer_user)

        response = client.post(f"/events/{event.id}/seats/instantiate/")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_uncovered_sections_returns_400_naming_sections(self, organizer_user):
        event = EventFactory(organizer=organizer_user, is_seated=True)
        SeatFactory(venue=event.venue, section="Balcony", row_label="A", seat_number=1)
        client = auth_client(organizer_user)

        response = client.post(f"/events/{event.id}/seats/instantiate/")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["sections"] == ["Balcony"]

    def test_double_instantiate_returns_409(self, organizer_user):
        event = _seated_approved_event(organizer=organizer_user)
        client = auth_client(organizer_user)
        client.post(f"/events/{event.id}/seats/instantiate/")

        response = client.post(f"/events/{event.id}/seats/instantiate/")
        assert response.status_code == status.HTTP_409_CONFLICT


# ==================================================
# POST /events/{id}/seats/hold/
# ==================================================


class TestHoldSeats:
    def _instantiated_event(self, organizer):
        event = _seated_approved_event(organizer=organizer)
        auth_client(organizer).post(f"/events/{event.id}/seats/instantiate/")
        return event

    def test_hold_returns_hold_id_and_seats(self, organizer_user, attendee_user):
        event = self._instantiated_event(organizer_user)
        seat_ids = list(
            EventSeat.objects.filter(event=event).values_list("id", flat=True)
        )
        client = auth_client(attendee_user)

        response = client.post(
            f"/events/{event.id}/seats/hold/", {"seat_ids": [str(s) for s in seat_ids]}
        )
        assert response.status_code == status.HTTP_200_OK
        assert "hold_id" in response.data
        assert "expires_at" in response.data
        assert len(response.data["seats"]) == len(seat_ids)
        assert all(s["status"] == "held" for s in response.data["seats"])

    def test_unauthenticated_cannot_hold(self, api_client, organizer_user):
        event = self._instantiated_event(organizer_user)
        seat_id = str(EventSeat.objects.filter(event=event).first().id)

        response = api_client.post(
            f"/events/{event.id}/seats/hold/", {"seat_ids": [seat_id]}
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_hold_conflict_returns_409_naming_seats(
        self, organizer_user, attendee_user
    ):
        event = self._instantiated_event(organizer_user)
        seat_id = str(EventSeat.objects.filter(event=event).first().id)
        auth_client(UserFactory(role="attendee")).post(
            f"/events/{event.id}/seats/hold/", {"seat_ids": [seat_id]}
        )

        response = auth_client(attendee_user).post(
            f"/events/{event.id}/seats/hold/", {"seat_ids": [seat_id]}
        )
        assert response.status_code == status.HTTP_409_CONFLICT
        assert {str(sid) for sid in response.data["seat_ids"]} == {seat_id}

    def test_over_cap_returns_400(self, organizer_user, attendee_user):
        event = self._instantiated_event(organizer_user)
        import uuid

        too_many = [str(uuid.uuid4()) for _ in range(MAX_SEATS_PER_HOLD + 1)]

        response = auth_client(attendee_user).post(
            f"/events/{event.id}/seats/hold/", {"seat_ids": too_many}
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_hold_against_non_approved_event_returns_409(self, organizer_user):
        event = EventFactory(
            organizer=organizer_user,
            is_seated=True,
            status=Event.Status.PENDING_APPROVAL,
        )
        seat = EventSeatFactory(event=event)

        response = auth_client(organizer_user).post(
            f"/events/{event.id}/seats/hold/", {"seat_ids": [str(seat.id)]}
        )
        assert response.status_code == status.HTTP_409_CONFLICT

    def test_attendee_cannot_see_or_hold_seats_on_pending_event(
        self, organizer_user, attendee_user
    ):
        event = EventFactory(
            organizer=organizer_user,
            is_seated=True,
            status=Event.Status.PENDING_APPROVAL,
        )
        seat = EventSeatFactory(event=event)

        response = auth_client(attendee_user).post(
            f"/events/{event.id}/seats/hold/", {"seat_ids": [str(seat.id)]}
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_hold_against_non_seated_event_returns_400(
        self, organizer_user, attendee_user
    ):
        event = EventFactory(
            organizer=organizer_user,
            is_seated=False,
            status=Event.Status.APPROVED,
        )

        response = auth_client(attendee_user).post(
            f"/events/{event.id}/seats/hold/", {"seat_ids": [str(uuid.uuid4())]}
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_hold_unknown_seat_id_returns_400_naming_seat_ids(
        self, organizer_user, attendee_user
    ):
        event = self._instantiated_event(organizer_user)
        unknown_id = str(uuid.uuid4())

        response = auth_client(attendee_user).post(
            f"/events/{event.id}/seats/hold/", {"seat_ids": [unknown_id]}
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert {str(sid) for sid in response.data["seat_ids"]} == {unknown_id}

    @pytest.mark.django_db(transaction=True)
    def test_hold_returns_409_when_seat_row_is_locked_by_another_transaction(
        self, organizer_user, attendee_user
    ):
        event = self._instantiated_event(organizer_user)
        seat_id = str(EventSeat.objects.filter(event=event).first().id)

        lock_acquired = threading.Event()
        release_lock = threading.Event()

        def hold_row_lock():
            with connection.cursor() as cursor:
                cursor.execute("BEGIN")
                cursor.execute(
                    "SELECT id FROM seating_eventseat WHERE id = %s FOR UPDATE",
                    [seat_id],
                )
                lock_acquired.set()
                release_lock.wait(timeout=10)
                cursor.execute("COMMIT")
            connection.close()

        locker = threading.Thread(target=hold_row_lock)
        locker.start()
        lock_acquired.wait(timeout=10)

        try:
            response = auth_client(attendee_user).post(
                f"/events/{event.id}/seats/hold/", {"seat_ids": [seat_id]}
            )
        finally:
            release_lock.set()
            locker.join(timeout=10)

        assert not locker.is_alive(), "locking thread hung — test setup is broken"
        assert response.status_code == status.HTTP_409_CONFLICT
        assert "being processed by another request" in response.data["detail"]
