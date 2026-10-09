import uuid
from unittest.mock import patch

import pytest
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.common.constants import Roles
from apps.events.factories import EventFactory, TicketTierFactory
from apps.seating.factories import EventSeatFactory
from apps.users.factories import UserFactory
from apps.venues.factories import VenueRequestFactory
from apps.venues.services import DuplicateSeatError
from tests.helpers import results

from ..factories import SeatFactory, VenueFactory
from ..models import Venue, VenueRequest

pytestmark = pytest.mark.django_db


def auth_client(user):
    client = APIClient()
    access = RefreshToken.for_user(user).access_token
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return client


@pytest.fixture
def admin():
    return UserFactory(role=Roles.ADMIN)


@pytest.fixture
def organizer():
    return UserFactory(role=Roles.ORGANIZER)


@pytest.fixture
def other_organizer():
    return UserFactory(role=Roles.ORGANIZER)


@pytest.fixture
def attendee():
    return UserFactory(role=Roles.ATTENDEE)


def _venue_payload(**overrides):
    payload = {
        "name": "New Arena",
        "address": "123 Main St",
        "city": "Nairobi",
        "country": "Kenya",
        "capacity": 500,
    }
    payload.update(overrides)
    return payload


# ==================================================
# GET /venues/ (list)
# ==================================================


class TestListVenues:
    url = "/venues/"

    def test_anonymous_can_list(self, api_client):
        VenueFactory()
        response = api_client.get(self.url)
        assert response.status_code == status.HTTP_200_OK

    def test_soft_deleted_venues_excluded_from_list(self, api_client):
        VenueFactory(name="Visible")
        VenueFactory(name="Hidden", is_active=False)
        response = api_client.get(self.url)
        names = [v["name"] for v in results(response)]
        assert "Visible" in names
        assert "Hidden" not in names

    def test_filter_by_city_is_case_insensitive(self, api_client):
        VenueFactory(name="Nairobi Arena", city="Nairobi")
        VenueFactory(name="Mombasa Arena", city="Mombasa")
        response = api_client.get(self.url, {"city": "NAIROBI"})
        names = [v["name"] for v in results(response)]
        assert names == ["Nairobi Arena"]


# ==================================================
# GET /venues/{id}/ (retrieve)
# ==================================================


class TestRetrieveVenue:
    def test_anonymous_can_retrieve(self, api_client):
        venue = VenueFactory()
        response = api_client.get(f"/venues/{venue.pk}/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["id"] == str(venue.pk)

    def test_retrieve_soft_deleted_venue_returns_404(self, api_client):
        venue = VenueFactory(is_active=False)
        response = api_client.get(f"/venues/{venue.pk}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_retrieve_nonexistent_venue_returns_404(self, api_client):
        response = api_client.get(f"/venues/{uuid.uuid4()}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND


# ==================================================
# POST /venues/ (create)
# ==================================================


class TestCreateVenue:
    url = "/venues/"

    def test_admin_can_create(self, admin):
        client = auth_client(admin)
        response = client.post(self.url, _venue_payload())
        assert response.status_code == status.HTTP_201_CREATED
        assert Venue.objects.filter(name="New Arena").exists()

    def test_anonymous_cannot_create(self, api_client):
        response = api_client.post(self.url, _venue_payload())
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_attendee_cannot_create(self, attendee):
        client = auth_client(attendee)
        response = client.post(self.url, _venue_payload())
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_organizer_cannot_create(self, organizer):
        client = auth_client(organizer)
        response = client.post(self.url, _venue_payload())
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_duplicate_name_and_city_rejected(self, admin):
        VenueFactory(name="Existing Arena", city="Nairobi")
        client = auth_client(admin)
        response = client.post(
            self.url, _venue_payload(name="Existing Arena", city="Nairobi")
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_invalid_capacity_rejected(self, admin):
        client = auth_client(admin)
        response = client.post(self.url, _venue_payload(capacity=0))
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_missing_fields_rejected(self, admin):
        client = auth_client(admin)
        response = client.post(self.url, {"name": "Incomplete Arena"})
        assert response.status_code == status.HTTP_400_BAD_REQUEST


# ==================================================
# PATCH /venues/{id}/ (update)
# ==================================================


class TestUpdateVenue:
    def test_admin_can_update(self, admin):
        venue = VenueFactory(name="Old Name")
        client = auth_client(admin)
        response = client.patch(f"/venues/{venue.pk}/", {"name": "New Name"})
        assert response.status_code == status.HTTP_200_OK
        venue.refresh_from_db()
        assert venue.name == "New Name"

    def test_attendee_cannot_update(self, attendee):
        venue = VenueFactory(name="Old Name")
        client = auth_client(attendee)
        response = client.patch(f"/venues/{venue.pk}/", {"name": "New Name"})
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_organizer_cannot_update(self, organizer):
        venue = VenueFactory(name="Old Name")
        client = auth_client(organizer)
        response = client.patch(f"/venues/{venue.pk}/", {"name": "New Name"})
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_anonymous_cannot_update(self, api_client):
        venue = VenueFactory(name="Old Name")
        response = api_client.patch(f"/venues/{venue.pk}/", {"name": "New Name"})
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_update_into_duplicate_name_and_city_rejected(self, admin):
        VenueFactory(name="Taken Name", city="Nairobi")
        venue = VenueFactory(name="Original Name", city="Nairobi")
        client = auth_client(admin)
        response = client.patch(f"/venues/{venue.pk}/", {"name": "Taken Name"})
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_put_is_not_allowed_even_for_admin(self, admin):
        venue = VenueFactory(name="Old Name")
        client = auth_client(admin)
        response = client.put(f"/venues/{venue.pk}/", _venue_payload())
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED


# ==================================================
# DELETE /venues/{id}/ (soft + hard delete)
# ==================================================


class TestDestroyVenue:
    def test_admin_soft_deletes_by_default(self, admin):
        venue = VenueFactory()
        client = auth_client(admin)
        response = client.delete(f"/venues/{venue.pk}/")
        assert response.status_code == status.HTTP_204_NO_CONTENT
        venue.refresh_from_db()
        assert venue.is_active is False
        assert Venue.all_objects.filter(pk=venue.pk).exists()

    def test_soft_delete_bumps_updated_at(self, admin):
        venue = VenueFactory()
        original_updated_at = venue.updated_at
        client = auth_client(admin)
        client.delete(f"/venues/{venue.pk}/")
        venue.refresh_from_db()
        assert venue.updated_at > original_updated_at

    def test_admin_hard_deletes_with_query_param(self, admin):
        venue = VenueFactory()
        client = auth_client(admin)
        response = client.delete(f"/venues/{venue.pk}/?hard=true")
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert Venue.all_objects.filter(pk=venue.pk).exists() is False

    def test_soft_deleting_already_inactive_venue_returns_404(self, admin):
        venue = VenueFactory(is_active=False)
        client = auth_client(admin)
        response = client.delete(f"/venues/{venue.pk}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_destroy_nonexistent_venue_returns_404(self, admin):
        client = auth_client(admin)
        response = client.delete(f"/venues/{uuid.uuid4()}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_attendee_cannot_delete(self, attendee):
        venue = VenueFactory()
        client = auth_client(attendee)
        response = client.delete(f"/venues/{venue.pk}/")
        assert response.status_code == status.HTTP_403_FORBIDDEN
        venue.refresh_from_db()
        assert venue.is_active is True

    def test_organizer_cannot_delete(self, organizer):
        venue = VenueFactory()
        client = auth_client(organizer)
        response = client.delete(f"/venues/{venue.pk}/")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_anonymous_cannot_delete(self, api_client):
        venue = VenueFactory()
        response = api_client.delete(f"/venues/{venue.pk}/")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_attendee_cannot_hard_delete(self, attendee):
        venue = VenueFactory()
        client = auth_client(attendee)
        response = client.delete(f"/venues/{venue.pk}/?hard=true")
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert Venue.all_objects.filter(pk=venue.pk).exists()


# ==================================================
# POST /venues/{id}/restore/
# ==================================================


class TestRestoreVenue:
    def test_admin_can_restore(self, admin):
        venue = VenueFactory(is_active=False)
        client = auth_client(admin)
        response = client.post(f"/venues/{venue.pk}/restore/")
        assert response.status_code == status.HTTP_200_OK
        venue.refresh_from_db()
        assert venue.is_active is True

    def test_restore_bumps_updated_at(self, admin):
        venue = VenueFactory(is_active=False)
        original_updated_at = venue.updated_at
        client = auth_client(admin)
        client.post(f"/venues/{venue.pk}/restore/")
        venue.refresh_from_db()
        assert venue.updated_at > original_updated_at

    def test_organizer_cannot_restore(self, organizer):
        venue = VenueFactory(is_active=False)
        client = auth_client(organizer)
        response = client.post(f"/venues/{venue.pk}/restore/")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_attendee_cannot_restore(self, attendee):
        venue = VenueFactory(is_active=False)
        client = auth_client(attendee)
        response = client.post(f"/venues/{venue.pk}/restore/")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_anonymous_cannot_restore(self, api_client):
        venue = VenueFactory(is_active=False)
        response = api_client.post(f"/venues/{venue.pk}/restore/")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_restoring_already_active_venue_returns_409(self, admin):
        venue = VenueFactory(is_active=True)
        client = auth_client(admin)
        response = client.post(f"/venues/{venue.pk}/restore/")
        assert response.status_code == status.HTTP_409_CONFLICT

    def test_restoring_nonexistent_venue_returns_404(self, admin):
        client = auth_client(admin)
        response = client.post(f"/venues/{uuid.uuid4()}/restore/")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_restore_blocked_by_conflicting_active_venue(self, admin):
        VenueFactory(name="Arena One", city="Nairobi", is_active=True)
        deleted = VenueFactory(name="Arena One", city="Nairobi", is_active=False)
        client = auth_client(admin)
        response = client.post(f"/venues/{deleted.pk}/restore/")
        assert response.status_code == status.HTTP_409_CONFLICT
        deleted.refresh_from_db()
        assert deleted.is_active is False


# ==================================================
# GET/POST /venues/{id}/seats/
# ==================================================


class TestVenueSeats:
    def _seat_template_payload(self):
        return {
            "sections": [
                {
                    "name": "Main Stand",
                    "rows": [{"row_label": "A", "seat_count": 10}],
                }
            ]
        }

    def test_organizer_can_view_seats(self, organizer):
        venue = VenueFactory()
        SeatFactory(venue=venue)
        client = auth_client(organizer)
        response = client.get(f"/venues/{venue.pk}/seats/")
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1

    def test_admin_can_view_seats(self, admin):
        venue = VenueFactory()
        client = auth_client(admin)
        response = client.get(f"/venues/{venue.pk}/seats/")
        assert response.status_code == status.HTTP_200_OK

    def test_attendee_cannot_view_seats(self, attendee):
        venue = VenueFactory()
        client = auth_client(attendee)
        response = client.get(f"/venues/{venue.pk}/seats/")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_anonymous_cannot_view_seats(self, api_client):
        venue = VenueFactory()
        response = api_client.get(f"/venues/{venue.pk}/seats/")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_organizer_cannot_create_seat_template(self, organizer):
        venue = VenueFactory(capacity=100)
        client = auth_client(organizer)
        response = client.post(
            f"/venues/{venue.pk}/seats/", self._seat_template_payload(), format="json"
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert venue.seats.count() == 0

    def test_admin_can_create_seat_template(self, admin):
        venue = VenueFactory(capacity=100)
        client = auth_client(admin)
        response = client.post(
            f"/venues/{venue.pk}/seats/", self._seat_template_payload(), format="json"
        )
        assert response.status_code == status.HTTP_201_CREATED

    def test_attendee_cannot_create_seat_template(self, attendee):
        venue = VenueFactory(capacity=100)
        client = auth_client(attendee)
        response = client.post(
            f"/venues/{venue.pk}/seats/", self._seat_template_payload(), format="json"
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_invalid_seat_payload_returns_400(self, admin):
        venue = VenueFactory(capacity=100)
        client = auth_client(admin)
        response = client.post(
            f"/venues/{venue.pk}/seats/", {"sections": []}, format="json"
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_seats_for_nonexistent_venue_returns_404(self, organizer):
        client = auth_client(organizer)
        response = client.get(f"/venues/{uuid.uuid4()}/seats/")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_organizer_reseed_attempt_is_forbidden(self, organizer):
        venue = VenueFactory(capacity=100)
        SeatFactory(venue=venue)
        client = auth_client(organizer)
        response = client.post(
            f"/venues/{venue.pk}/seats/", self._seat_template_payload(), format="json"
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert venue.seats.count() == 1

    def test_admin_can_reseed_existing_template(self, admin):
        venue = VenueFactory(capacity=100)
        SeatFactory(venue=venue, section="Original")
        client = auth_client(admin)
        response = client.post(
            f"/venues/{venue.pk}/seats/", self._seat_template_payload(), format="json"
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert venue.seats.count() == 10
        assert not venue.seats.filter(section="Original").exists()

    def test_admin_reseed_blocked_when_seat_in_use_by_an_event(self, admin):
        venue = VenueFactory(capacity=100)
        seat = SeatFactory(venue=venue, section="Original")
        event = EventFactory(venue=venue)
        tier = TicketTierFactory(event=event)
        EventSeatFactory(event=event, seat=seat, ticket_tier=tier)

        client = auth_client(admin)
        response = client.post(
            f"/venues/{venue.pk}/seats/", self._seat_template_payload(), format="json"
        )
        assert response.status_code == status.HTTP_409_CONFLICT
        assert venue.seats.count() == 1

    def test_capacity_exceeded_returns_409(self, admin):
        venue = VenueFactory(capacity=5)
        client = auth_client(admin)
        response = client.post(
            f"/venues/{venue.pk}/seats/", self._seat_template_payload(), format="json"
        )
        assert response.status_code == status.HTTP_409_CONFLICT
        assert venue.seats.count() == 0

    def test_duplicate_seat_error_from_service_maps_to_409(self, admin):
        venue = VenueFactory(capacity=100)
        client = auth_client(admin)
        with patch(
            "apps.venues.views.bulk_create_seat_template",
            side_effect=DuplicateSeatError("Duplicate seat detected."),
        ):
            response = client.post(
                f"/venues/{venue.pk}/seats/",
                self._seat_template_payload(),
                format="json",
            )
        assert response.status_code == status.HTTP_409_CONFLICT


def _client(user):
    client = APIClient(raise_request_exception=False)
    client.force_authenticate(user)
    return client


def test_venue_request_notes_are_length_capped():
    organizer = UserFactory(role=Roles.ORGANIZER)
    response = _client(organizer).post(
        "/venues/requests/",
        {"venue_name": "Arena", "city": "Karachi", "notes": "x" * 2001},
        format="json",
    )
    assert response.status_code == 400


def test_venue_request_submissions_are_throttled(settings):
    from django.core.cache import cache

    cache.clear()
    organizer = UserFactory(role=Roles.ORGANIZER)
    client = _client(organizer)
    codes = [
        client.post(
            "/venues/requests/",
            {"venue_name": f"Arena {i}", "city": "Karachi"},
            format="json",
        ).status_code
        for i in range(12)
    ]
    assert codes[:10] == [201] * 10
    assert 429 in codes[10:]


def test_reject_with_non_string_admin_notes_is_a_400():
    admin = UserFactory(role=Roles.ADMIN)
    request = VenueRequestFactory()
    response = _client(admin).post(
        f"/venues/requests/{request.id}/reject/", {"admin_notes": ["x"]}, format="json"
    )
    assert response.status_code == 400


@pytest.mark.django_db
class TestProtectedHardDelete:
    def test_hard_deleting_a_venue_with_event_history_is_a_409(self):
        admin = UserFactory(role=Roles.ADMIN)
        venue = VenueFactory()
        event = EventFactory(venue=venue, status="cancelled")
        EventSeatFactory(
            event=event,
            ticket_tier=TicketTierFactory(event=event),
            seat=SeatFactory(venue=venue),
        )
        client = APIClient(raise_request_exception=False)
        client.force_authenticate(admin)

        response = client.delete(f"/venues/{venue.id}/?hard=true")

        assert response.status_code == 409
        assert Venue.all_objects.filter(id=venue.id).exists()


# ==================================================
# POST /venues/requests/
# ==================================================


class TestCreateVenueRequest:
    url = "/venues/requests/"

    def test_organizer_can_create(self, organizer):
        client = auth_client(organizer)
        payload = {
            "venue_name": "The Grand Hall",
            "city": "Karachi",
            "notes": "500-seat capacity",
        }
        response = client.post(self.url, payload)
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["status"] == VenueRequest.Status.PENDING
        assert response.data["requested_by"] == organizer.pk

        request = VenueRequest.objects.get(pk=response.data["id"])
        assert request.requested_by == organizer

    def test_duplicate_pending_requests_from_same_organizer_are_allowed(
        self, organizer
    ):
        client = auth_client(organizer)
        payload = {"venue_name": "Same Venue", "city": "Karachi"}
        first = client.post(self.url, payload)
        second = client.post(self.url, payload)
        assert first.status_code == status.HTTP_201_CREATED
        assert second.status_code == status.HTTP_201_CREATED
        assert VenueRequest.objects.filter(venue_name="Same Venue").count() == 2

    def test_admin_cannot_create(self, admin):
        client = auth_client(admin)
        response = client.post(self.url, {"venue_name": "X", "city": "Y"})
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_attendee_cannot_create(self, attendee):
        client = auth_client(attendee)
        response = client.post(self.url, {"venue_name": "X", "city": "Y"})
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_anonymous_cannot_create(self, api_client):
        response = api_client.post(self.url, {"venue_name": "X", "city": "Y"})
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_requested_by_cannot_be_spoofed(self, organizer, other_organizer):
        client = auth_client(organizer)
        response = client.post(
            self.url,
            {
                "venue_name": "X",
                "city": "Y",
                "requested_by": str(other_organizer.pk),
            },
        )
        assert response.status_code == status.HTTP_201_CREATED
        request = VenueRequest.objects.get(pk=response.data["id"])
        assert request.requested_by == organizer


# ==================================================
# GET /venues/requests/
# ==================================================


class TestListVenueRequests:
    url = "/venues/requests/"

    def test_organizer_sees_only_their_own(self, organizer, other_organizer):
        mine = VenueRequestFactory(requested_by=organizer)
        VenueRequestFactory(requested_by=other_organizer)

        response = auth_client(organizer).get(self.url)

        ids = {row["id"] for row in results(response)}
        assert ids == {str(mine.pk)}

    def test_admin_sees_all(self, admin, organizer, other_organizer):
        first = VenueRequestFactory(requested_by=organizer)
        second = VenueRequestFactory(requested_by=other_organizer)

        response = auth_client(admin).get(self.url)

        ids = {row["id"] for row in results(response)}
        assert ids == {str(first.pk), str(second.pk)}

    def test_ordered_oldest_first(self, admin):
        first = VenueRequestFactory()
        second = VenueRequestFactory()

        response = auth_client(admin).get(self.url)

        ids = [row["id"] for row in results(response)]
        assert ids == [str(first.pk), str(second.pk)]

    def test_anonymous_rejected(self, api_client):
        response = api_client.get(self.url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


# ==================================================
# POST /venues/requests/{id}/reject/
# ==================================================


class TestRejectVenueRequest:
    def url(self, venue_request):
        return f"/venues/requests/{venue_request.pk}/reject/"

    def test_admin_can_reject_with_notes(self, admin):
        venue_request = VenueRequestFactory()
        response = auth_client(admin).post(
            self.url(venue_request), {"admin_notes": "No capacity data provided."}
        )
        assert response.status_code == status.HTTP_200_OK
        venue_request.refresh_from_db()
        assert venue_request.status == VenueRequest.Status.REJECTED
        assert venue_request.admin_notes == "No capacity data provided."
        assert venue_request.reviewed_at is not None

    def test_blank_admin_notes_returns_400(self, admin):
        venue_request = VenueRequestFactory()
        response = auth_client(admin).post(
            self.url(venue_request), {"admin_notes": "   "}
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_missing_admin_notes_returns_400(self, admin):
        venue_request = VenueRequestFactory()
        response = auth_client(admin).post(self.url(venue_request))
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_reject_non_pending_returns_409(self, admin):
        venue_request = VenueRequestFactory(status=VenueRequest.Status.FULFILLED)
        response = auth_client(admin).post(
            self.url(venue_request), {"admin_notes": "Late."}
        )
        assert response.status_code == status.HTTP_409_CONFLICT

    def test_organizer_cannot_reject(self, organizer):
        venue_request = VenueRequestFactory()
        response = auth_client(organizer).post(
            self.url(venue_request), {"admin_notes": "Nice try."}
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN


# ==================================================
# POST /venues/requests/{id}/fulfil/
# ==================================================


class TestFulfilVenueRequest:
    def url(self, venue_request):
        return f"/venues/requests/{venue_request.pk}/fulfil/"

    def test_admin_can_fulfil(self, admin):
        venue_request = VenueRequestFactory()
        response = auth_client(admin).post(self.url(venue_request))
        assert response.status_code == status.HTTP_200_OK
        venue_request.refresh_from_db()
        assert venue_request.status == VenueRequest.Status.FULFILLED
        assert venue_request.reviewed_at is not None

    def test_fulfil_never_creates_a_venue_as_a_side_effect(self, admin):
        venue_request = VenueRequestFactory(venue_name="Never Auto-Created Arena")
        before_count = Venue.objects.count()

        auth_client(admin).post(self.url(venue_request))

        assert Venue.objects.count() == before_count
        assert not Venue.objects.filter(name="Never Auto-Created Arena").exists()

    def test_fulfil_non_pending_returns_409(self, admin):
        venue_request = VenueRequestFactory(status=VenueRequest.Status.REJECTED)
        response = auth_client(admin).post(self.url(venue_request))
        assert response.status_code == status.HTTP_409_CONFLICT

    def test_organizer_cannot_fulfil(self, organizer):
        venue_request = VenueRequestFactory()
        response = auth_client(organizer).post(self.url(venue_request))
        assert response.status_code == status.HTTP_403_FORBIDDEN
