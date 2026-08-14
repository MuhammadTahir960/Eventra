import pytest
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.common.constants import Roles
from apps.events.factories import EventFactory
from apps.events.models import Event
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

    def test_admin_can_update_name(self, admin):
        sport = SportFactory(name="Football")
        client = auth_client(admin)
        response = client.patch(f"/sports/{sport.pk}/", {"name": "Soccer"})
        assert response.status_code == status.HTTP_200_OK
        sport.refresh_from_db()
        assert sport.name == "Soccer"

    def test_anonymous_cannot_update(self, api_client):
        sport = SportFactory()
        response = api_client.patch(f"/sports/{sport.pk}/", {"name": "Renamed"})
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_attendee_cannot_update(self, attendee):
        sport = SportFactory()
        client = auth_client(attendee)
        response = client.patch(f"/sports/{sport.pk}/", {"name": "Renamed"})
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_organizer_cannot_update(self, organizer):
        sport = SportFactory()
        client = auth_client(organizer)
        response = client.patch(f"/sports/{sport.pk}/", {"name": "Renamed"})
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_admin_can_delete_unreferenced_sport(self, admin):
        sport = SportFactory()
        client = auth_client(admin)
        response = client.delete(f"/sports/{sport.pk}/")
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not Sport.objects.filter(pk=sport.pk).exists()

    def test_admin_cannot_delete_sport_referenced_via_team(self, admin):
        sport = SportFactory()
        home = TeamFactory(sport=sport)
        away = TeamFactory(sport=sport)
        EventFactory(
            event_type=Event.EventType.SPORTS_MATCH, home_team=home, away_team=away
        )
        client = auth_client(admin)
        response = client.delete(f"/sports/{sport.pk}/")
        assert response.status_code == status.HTTP_409_CONFLICT
        assert Sport.objects.filter(pk=sport.pk).exists()

    def test_anonymous_cannot_delete(self, api_client):
        sport = SportFactory()
        response = api_client.delete(f"/sports/{sport.pk}/")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_organizer_cannot_delete(self, organizer):
        sport = SportFactory()
        client = auth_client(organizer)
        response = client.delete(f"/sports/{sport.pk}/")
        assert response.status_code == status.HTTP_403_FORBIDDEN


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

    def test_admin_can_update_name(self, admin):
        league = LeagueFactory(name="Premier League")
        client = auth_client(admin)
        response = client.patch(f"/leagues/{league.pk}/", {"name": "EPL"})
        assert response.status_code == status.HTTP_200_OK
        league.refresh_from_db()
        assert league.name == "EPL"

    def test_anonymous_cannot_update(self, api_client):
        league = LeagueFactory()
        response = api_client.patch(f"/leagues/{league.pk}/", {"name": "Renamed"})
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_attendee_cannot_update(self, attendee):
        league = LeagueFactory()
        client = auth_client(attendee)
        response = client.patch(f"/leagues/{league.pk}/", {"name": "Renamed"})
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_organizer_cannot_update(self, organizer):
        league = LeagueFactory()
        client = auth_client(organizer)
        response = client.patch(f"/leagues/{league.pk}/", {"name": "Renamed"})
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_admin_can_reassign_sport_when_unreferenced(self, admin):
        league = LeagueFactory()
        new_sport = SportFactory()
        client = auth_client(admin)
        response = client.patch(f"/leagues/{league.pk}/", {"sport": str(new_sport.pk)})
        assert response.status_code == status.HTTP_200_OK
        league.refresh_from_db()
        assert league.sport_id == new_sport.id

    def test_admin_cannot_reassign_sport_when_referenced_by_event(self, admin):
        league = LeagueFactory()
        EventFactory(event_type=Event.EventType.SPORTS_MATCH, league=league)
        new_sport = SportFactory()
        client = auth_client(admin)
        response = client.patch(f"/leagues/{league.pk}/", {"sport": str(new_sport.pk)})
        assert response.status_code == status.HTTP_409_CONFLICT
        league.refresh_from_db()
        assert league.sport_id != new_sport.id

    def test_resending_same_sport_is_not_blocked_even_when_referenced(self, admin):
        league = LeagueFactory()
        EventFactory(event_type=Event.EventType.SPORTS_MATCH, league=league)
        client = auth_client(admin)
        response = client.patch(
            f"/leagues/{league.pk}/",
            {"sport": str(league.sport_id), "name": "Renamed League"},
        )
        assert response.status_code == status.HTTP_200_OK
        league.refresh_from_db()
        assert league.name == "Renamed League"

    def test_name_only_update_not_blocked_when_referenced(self, admin):
        league = LeagueFactory()
        EventFactory(event_type=Event.EventType.SPORTS_MATCH, league=league)
        client = auth_client(admin)
        response = client.patch(f"/leagues/{league.pk}/", {"name": "New Name"})
        assert response.status_code == status.HTTP_200_OK

    def test_admin_can_delete_unreferenced_league(self, admin):
        league = LeagueFactory()
        client = auth_client(admin)
        response = client.delete(f"/leagues/{league.pk}/")
        assert response.status_code == status.HTTP_204_NO_CONTENT

    def test_admin_cannot_delete_league_referenced_by_event(self, admin):
        league = LeagueFactory()
        EventFactory(event_type=Event.EventType.SPORTS_MATCH, league=league)
        client = auth_client(admin)
        response = client.delete(f"/leagues/{league.pk}/")
        assert response.status_code == status.HTTP_409_CONFLICT

    def test_anonymous_cannot_delete(self, api_client):
        league = LeagueFactory()
        response = api_client.delete(f"/leagues/{league.pk}/")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_organizer_cannot_delete(self, organizer):
        league = LeagueFactory()
        client = auth_client(organizer)
        response = client.delete(f"/leagues/{league.pk}/")
        assert response.status_code == status.HTTP_403_FORBIDDEN

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

    def test_admin_can_update_name(self, admin):
        team = TeamFactory(name="Arsenal")
        client = auth_client(admin)
        response = client.patch(f"/teams/{team.pk}/", {"name": "Arsenal FC"})
        assert response.status_code == status.HTTP_200_OK
        team.refresh_from_db()
        assert team.name == "Arsenal FC"

    def test_anonymous_cannot_update(self, api_client):
        team = TeamFactory()
        response = api_client.patch(f"/teams/{team.pk}/", {"name": "Renamed"})
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_attendee_cannot_update(self, attendee):
        team = TeamFactory()
        client = auth_client(attendee)
        response = client.patch(f"/teams/{team.pk}/", {"name": "Renamed"})
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_organizer_cannot_update(self, organizer):
        team = TeamFactory()
        client = auth_client(organizer)
        response = client.patch(f"/teams/{team.pk}/", {"name": "Renamed"})
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_admin_can_reassign_sport_when_unreferenced(self, admin):
        team = TeamFactory()
        new_sport = SportFactory()
        client = auth_client(admin)
        response = client.patch(f"/teams/{team.pk}/", {"sport": str(new_sport.pk)})
        assert response.status_code == status.HTTP_200_OK
        team.refresh_from_db()
        assert team.sport_id == new_sport.id

    def test_admin_cannot_reassign_sport_when_referenced_as_home_team(self, admin):
        sport = SportFactory()
        home = TeamFactory(sport=sport)
        away = TeamFactory(sport=sport)
        EventFactory(
            event_type=Event.EventType.SPORTS_MATCH, home_team=home, away_team=away
        )
        new_sport = SportFactory()
        client = auth_client(admin)
        response = client.patch(f"/teams/{home.pk}/", {"sport": str(new_sport.pk)})
        assert response.status_code == status.HTTP_409_CONFLICT
        home.refresh_from_db()
        assert home.sport_id != new_sport.id

    def test_admin_cannot_reassign_sport_when_referenced_as_away_team(self, admin):
        sport = SportFactory()
        home = TeamFactory(sport=sport)
        away = TeamFactory(sport=sport)
        EventFactory(
            event_type=Event.EventType.SPORTS_MATCH, home_team=home, away_team=away
        )
        new_sport = SportFactory()
        client = auth_client(admin)
        response = client.patch(f"/teams/{away.pk}/", {"sport": str(new_sport.pk)})
        assert response.status_code == status.HTTP_409_CONFLICT

    def test_resending_same_sport_is_not_blocked_even_when_referenced(self, admin):
        sport = SportFactory()
        home = TeamFactory(sport=sport)
        away = TeamFactory(sport=sport)
        EventFactory(
            event_type=Event.EventType.SPORTS_MATCH, home_team=home, away_team=away
        )
        client = auth_client(admin)
        response = client.patch(
            f"/teams/{home.pk}/",
            {"sport": str(home.sport_id), "name": "Renamed Team"},
        )
        assert response.status_code == status.HTTP_200_OK
        home.refresh_from_db()
        assert home.name == "Renamed Team"

    def test_name_only_update_not_blocked_when_referenced(self, admin):
        sport = SportFactory()
        home = TeamFactory(sport=sport)
        away = TeamFactory(sport=sport)
        EventFactory(
            event_type=Event.EventType.SPORTS_MATCH, home_team=home, away_team=away
        )
        client = auth_client(admin)
        response = client.patch(f"/teams/{home.pk}/", {"name": "New Name"})
        assert response.status_code == status.HTTP_200_OK

    def test_admin_can_delete_unreferenced_team(self, admin):
        team = TeamFactory()
        client = auth_client(admin)
        response = client.delete(f"/teams/{team.pk}/")
        assert response.status_code == status.HTTP_204_NO_CONTENT

    def test_admin_cannot_delete_team_referenced_as_home_team(self, admin):
        sport = SportFactory()
        home = TeamFactory(sport=sport)
        away = TeamFactory(sport=sport)
        EventFactory(
            event_type=Event.EventType.SPORTS_MATCH, home_team=home, away_team=away
        )
        client = auth_client(admin)
        response = client.delete(f"/teams/{home.pk}/")
        assert response.status_code == status.HTTP_409_CONFLICT

    def test_admin_cannot_delete_team_referenced_as_away_team(self, admin):
        sport = SportFactory()
        home = TeamFactory(sport=sport)
        away = TeamFactory(sport=sport)
        EventFactory(
            event_type=Event.EventType.SPORTS_MATCH, home_team=home, away_team=away
        )
        client = auth_client(admin)
        response = client.delete(f"/teams/{away.pk}/")
        assert response.status_code == status.HTTP_409_CONFLICT

    def test_anonymous_cannot_delete(self, api_client):
        team = TeamFactory()
        response = api_client.delete(f"/teams/{team.pk}/")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_organizer_cannot_delete(self, organizer):
        team = TeamFactory()
        client = auth_client(organizer)
        response = client.delete(f"/teams/{team.pk}/")
        assert response.status_code == status.HTTP_403_FORBIDDEN
