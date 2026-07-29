import pytest
from apps.sports.services import (
    DuplicateLeagueError,
    DuplicateSportError,
    DuplicateTeamError,
    ensure_unique_league_name,
    ensure_unique_sport_name,
    ensure_unique_team_name,
)
from ..factories import LeagueFactory, SportFactory, TeamFactory

pytestmark = pytest.mark.django_db


# ==================================================
# ensure_unique_sport_name
# ==================================================


def test_sport_name_free_raises_nothing():
    ensure_unique_sport_name("Football")


def test_sport_name_taken_raises_duplicate_error():
    SportFactory(name="Football")
    with pytest.raises(DuplicateSportError):
        ensure_unique_sport_name("Football")


def test_sport_name_check_is_case_insensitive():
    SportFactory(name="Football")
    with pytest.raises(DuplicateSportError):
        ensure_unique_sport_name("FOOTBALL")


def test_sport_exclude_pk_allows_keeping_same_name():
    sport = SportFactory(name="Football")
    ensure_unique_sport_name("Football", exclude_pk=sport.pk)


# ==================================================
# ensure_unique_league_name
# ==================================================


def test_league_name_free_raises_nothing():
    sport = SportFactory()
    ensure_unique_league_name(sport, "Premier League")


def test_league_name_taken_within_sport_raises_duplicate_error():
    sport = SportFactory()
    LeagueFactory(sport=sport, name="Premier League")
    with pytest.raises(DuplicateLeagueError):
        ensure_unique_league_name(sport, "Premier League")


def test_league_name_check_is_case_insensitive():
    sport = SportFactory()
    LeagueFactory(sport=sport, name="Premier League")
    with pytest.raises(DuplicateLeagueError):
        ensure_unique_league_name(sport, "PREMIER LEAGUE")


def test_league_name_taken_in_different_sport_does_not_conflict():
    LeagueFactory(sport=SportFactory(), name="Premier League")
    other_sport = SportFactory()
    ensure_unique_league_name(other_sport, "Premier League")


def test_league_exclude_pk_allows_keeping_same_name():
    sport = SportFactory()
    league = LeagueFactory(sport=sport, name="Premier League")
    ensure_unique_league_name(sport, "Premier League", exclude_pk=league.pk)


# ==================================================
# ensure_unique_team_name
# ==================================================


def test_team_name_free_raises_nothing():
    sport = SportFactory()
    ensure_unique_team_name(sport, "Arsenal")


def test_team_name_taken_within_sport_raises_duplicate_error():
    sport = SportFactory()
    TeamFactory(sport=sport, name="Arsenal")
    with pytest.raises(DuplicateTeamError):
        ensure_unique_team_name(sport, "Arsenal")


def test_team_name_check_is_case_insensitive():
    sport = SportFactory()
    TeamFactory(sport=sport, name="Arsenal")
    with pytest.raises(DuplicateTeamError):
        ensure_unique_team_name(sport, "ARSENAL")


def test_team_name_taken_in_different_sport_does_not_conflict():
    TeamFactory(sport=SportFactory(), name="Arsenal")
    other_sport = SportFactory()
    ensure_unique_team_name(other_sport, "Arsenal")


def test_team_exclude_pk_allows_keeping_same_name():
    sport = SportFactory()
    team = TeamFactory(sport=sport, name="Arsenal")
    ensure_unique_team_name(sport, "Arsenal", exclude_pk=team.pk)
