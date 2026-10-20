import pytest
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.common.constants import Roles
from apps.users.factories import UserFactory

from ..factories import VenueFactory
from ..models import Venue

pytestmark = pytest.mark.django_db


def auth_client(user):
    client = APIClient()
    access = RefreshToken.for_user(user).access_token
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return client


def _payload(**overrides):
    payload = {
        "name": "Shape Arena",
        "address": "1 Stadium Rd",
        "city": "Karachi",
        "country": "Pakistan",
        "capacity": 500,
    }
    payload.update(overrides)
    return payload


class TestVenueLayoutShape:
    def test_defaults_to_oval_and_is_public(self):
        venue = VenueFactory()

        response = APIClient().get(f"/venues/{venue.id}/")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["layout_shape"] == Venue.LayoutShape.OVAL

    def test_admin_can_create_with_a_shape(self):
        admin = UserFactory(role=Roles.ADMIN)

        response = auth_client(admin).post(
            "/venues/", _payload(layout_shape="u_shape"), format="json"
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["layout_shape"] == "u_shape"

    def test_create_without_a_shape_uses_the_default(self):
        admin = UserFactory(role=Roles.ADMIN)

        response = auth_client(admin).post("/venues/", _payload(), format="json")

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["layout_shape"] == "oval"

    def test_unknown_shape_is_rejected(self):
        admin = UserFactory(role=Roles.ADMIN)

        response = auth_client(admin).post(
            "/venues/", _payload(layout_shape="triangle"), format="json"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "layout_shape" in response.data

    def test_admin_can_change_the_shape(self):
        admin = UserFactory(role=Roles.ADMIN)
        venue = VenueFactory()

        response = auth_client(admin).patch(
            f"/venues/{venue.id}/", {"layout_shape": "circle"}, format="json"
        )

        assert response.status_code == status.HTTP_200_OK
        venue.refresh_from_db()
        assert venue.layout_shape == Venue.LayoutShape.CIRCLE

    def test_organizer_cannot_change_the_shape(self):
        organizer = UserFactory(role=Roles.ORGANIZER)
        venue = VenueFactory()

        response = auth_client(organizer).patch(
            f"/venues/{venue.id}/", {"layout_shape": "circle"}, format="json"
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
        venue.refresh_from_db()
        assert venue.layout_shape == Venue.LayoutShape.OVAL
