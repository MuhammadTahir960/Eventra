import pytest
import uuid
from unittest.mock import patch
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken
from apps.common.constants import Roles
from apps.users.factories import UserFactory
from apps.venues.services import DuplicateSeatError
from tests.helpers import results
from ..models import Venue
from ..factories import SeatFactory, VenueFactory

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

    def test_organizer_can_create_seat_template(self, organizer):
        venue = VenueFactory(capacity=100)
        client = auth_client(organizer)
        response = client.post(
            f"/venues/{venue.pk}/seats/", self._seat_template_payload(), format="json"
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert venue.seats.count() == 10

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

    def test_invalid_seat_payload_returns_400(self, organizer):
        venue = VenueFactory(capacity=100)
        client = auth_client(organizer)
        response = client.post(
            f"/venues/{venue.pk}/seats/", {"sections": []}, format="json"
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_seats_for_nonexistent_venue_returns_404(self, organizer):
        client = auth_client(organizer)
        response = client.get(f"/venues/{uuid.uuid4()}/seats/")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_organizer_reseed_attempt_returns_409(self, organizer):
        venue = VenueFactory(capacity=100)
        SeatFactory(venue=venue)
        client = auth_client(organizer)
        response = client.post(
            f"/venues/{venue.pk}/seats/", self._seat_template_payload(), format="json"
        )
        assert response.status_code == status.HTTP_409_CONFLICT
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

    def test_capacity_exceeded_returns_409(self, organizer):
        venue = VenueFactory(capacity=5)
        client = auth_client(organizer)
        response = client.post(
            f"/venues/{venue.pk}/seats/", self._seat_template_payload(), format="json"
        )
        assert response.status_code == status.HTTP_409_CONFLICT
        assert venue.seats.count() == 0

    def test_duplicate_seat_error_from_service_maps_to_409(self, organizer):
        venue = VenueFactory(capacity=100)
        client = auth_client(organizer)
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
