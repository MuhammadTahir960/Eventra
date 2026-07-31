import pytest
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken
from apps.common.constants import Roles
from apps.sports.models import Sport
from apps.users.factories import UserFactory
from tests.helpers import results
from ..factories import LeagueFactory, SportFactory, TeamFactory

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


# ==================================================
# /sports/
# ==================================================


class TestSportEndpoint:
    url = "/sports/"

    def test_anonymous_can_list(self, api_client):
        SportFactory()
        response = api_client.get(self.url)
        assert response.status_code == status.HTTP_200_OK

    def test_admin_can_create(self, admin):
        client = auth_client(admin)
        response = client.post(self.url, {"name": "Football"})
        assert response.status_code == status.HTTP_201_CREATED
        assert Sport.objects.filter(name="Football").exists()

    def test_anonymous_cannot_create(self, api_client):
        response = api_client.post(self.url, {"name": "Football"})
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_attendee_cannot_create(self, attendee):
        client = auth_client(attendee)
        response = client.post(self.url, {"name": "Football"})
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_organizer_cannot_create(self, organizer):
        client = auth_client(organizer)
        response = client.post(self.url, {"name": "Football"})
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_duplicate_name_rejected(self, admin):
        SportFactory(name="Football")
        client = auth_client(admin)
        response = client.post(self.url, {"name": "Football"})
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_blank_name_rejected(self, admin):
        client = auth_client(admin)
        response = client.post(self.url, {"name": "   "})
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_no_update_or_delete_endpoints_exposed(self, admin):
        sport = SportFactory()
        client = auth_client(admin)
        response = client.patch(f"/sports/{sport.pk}/", {"name": "Renamed"})
        assert response.status_code == status.HTTP_404_NOT_FOUND


# ==================================================
# /leagues/
# ==================================================


class TestLeagueEndpoint:
    url = "/leagues/"

    def test_anonymous_can_list(self, api_client):
        LeagueFactory()
        response = api_client.get(self.url)
        assert response.status_code == status.HTTP_200_OK

    def test_admin_can_create(self, admin):
        sport = SportFactory()
        client = auth_client(admin)
        response = client.post(
            self.url, {"sport": str(sport.pk), "name": "Premier League"}
        )
        assert response.status_code == status.HTTP_201_CREATED

    def test_attendee_cannot_create(self, attendee):
        sport = SportFactory()
        client = auth_client(attendee)
        response = client.post(
            self.url, {"sport": str(sport.pk), "name": "Premier League"}
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_organizer_cannot_create(self, organizer):
        sport = SportFactory()
        client = auth_client(organizer)
        response = client.post(
            self.url, {"sport": str(sport.pk), "name": "Premier League"}
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_anonymous_cannot_create(self, api_client):
        sport = SportFactory()
        response = api_client.post(
            self.url, {"sport": str(sport.pk), "name": "Premier League"}
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_blank_name_rejected(self, admin):
        sport = SportFactory()
        client = auth_client(admin)
        response = client.post(self.url, {"sport": str(sport.pk), "name": "   "})
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_no_update_or_delete_endpoints_exposed(self, admin):
        league = LeagueFactory()
        client = auth_client(admin)
        response = client.patch(f"/leagues/{league.pk}/", {"name": "Renamed"})
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_duplicate_name_within_sport_rejected(self, admin):
        sport = SportFactory()
        LeagueFactory(sport=sport, name="Premier League")
        client = auth_client(admin)
        response = client.post(
            self.url, {"sport": str(sport.pk), "name": "Premier League"}
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_filter_by_sport_returns_only_matching_leagues(self, api_client):
        sport_a = SportFactory()
        sport_b = SportFactory()
        LeagueFactory(sport=sport_a, name="League A")
        LeagueFactory(sport=sport_b, name="League B")
        response = api_client.get(self.url, {"sport": str(sport_a.pk)})
        names = [item["name"] for item in results(response)]
        assert names == ["League A"]

    def test_filter_by_nonexistent_sport_returns_empty(self, api_client):
        import uuid

        LeagueFactory()
        response = api_client.get(self.url, {"sport": str(uuid.uuid4())})
        assert results(response) == []

    def test_invalid_sport_filter_value_returns_400(self, api_client):
        LeagueFactory()
        response = api_client.get(self.url, {"sport": "not-a-uuid"})
        assert response.status_code == status.HTTP_400_BAD_REQUEST


# ==================================================
# /teams/
# ==================================================


class TestTeamEndpoint:
    url = "/teams/"

    def test_anonymous_can_list(self, api_client):
        TeamFactory()
        response = api_client.get(self.url)
        assert response.status_code == status.HTTP_200_OK

    def test_admin_can_create(self, admin):
        sport = SportFactory()
        client = auth_client(admin)
        response = client.post(self.url, {"sport": str(sport.pk), "name": "Arsenal"})
        assert response.status_code == status.HTTP_201_CREATED

    def test_attendee_cannot_create(self, attendee):
        sport = SportFactory()
        client = auth_client(attendee)
        response = client.post(self.url, {"sport": str(sport.pk), "name": "Arsenal"})
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_organizer_cannot_create(self, organizer):
        sport = SportFactory()
        client = auth_client(organizer)
        response = client.post(self.url, {"sport": str(sport.pk), "name": "Arsenal"})
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_anonymous_cannot_create(self, api_client):
        sport = SportFactory()
        response = api_client.post(
            self.url, {"sport": str(sport.pk), "name": "Arsenal"}
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_blank_name_rejected(self, admin):
        sport = SportFactory()
        client = auth_client(admin)
        response = client.post(self.url, {"sport": str(sport.pk), "name": "   "})
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_duplicate_name_within_sport_rejected(self, admin):
        sport = SportFactory()
        TeamFactory(sport=sport, name="Arsenal")
        client = auth_client(admin)
        response = client.post(self.url, {"sport": str(sport.pk), "name": "Arsenal"})
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_filter_by_sport_returns_only_matching_teams(self, api_client):
        sport_a = SportFactory()
        sport_b = SportFactory()
        TeamFactory(sport=sport_a, name="Team A")
        TeamFactory(sport=sport_b, name="Team B")
        response = api_client.get(self.url, {"sport": str(sport_a.pk)})
        names = [item["name"] for item in results(response)]
        assert names == ["Team A"]

    def test_filter_by_nonexistent_sport_returns_empty(self, api_client):
        import uuid

        TeamFactory()
        response = api_client.get(self.url, {"sport": str(uuid.uuid4())})
        assert results(response) == []

    def test_invalid_sport_filter_value_returns_400(self, api_client):
        TeamFactory()
        response = api_client.get(self.url, {"sport": "not-a-uuid"})
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_no_update_or_delete_endpoints_exposed(self, admin):
        team = TeamFactory()
        client = auth_client(admin)
        response = client.patch(f"/teams/{team.pk}/", {"name": "Renamed"})
        assert response.status_code == status.HTTP_404_NOT_FOUND

        response = client.delete(f"/teams/{team.pk}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND
