import pytest
from django.db import IntegrityError

from ..factories import LeagueFactory, SportFactory, TeamFactory
from ..models import League, Sport, Team

pytestmark = pytest.mark.django_db


# ==================================================
# Sport — global case-insensitive uniqueness
# ==================================================


def test_duplicate_sport_name_rejected_at_db_level():
    SportFactory(name="Football")
    with pytest.raises(IntegrityError):
        SportFactory(name="Football")


def test_duplicate_sport_name_case_insensitive_rejected_at_db_level():
    SportFactory(name="Football")
    with pytest.raises(IntegrityError):
        SportFactory(name="FOOTBALL")


def test_sport_str_returns_name():
    sport = SportFactory(name="Basketball")
    assert str(sport) == "Basketball"


def test_sports_ordered_by_name():
    SportFactory(name="Zebra Sport")
    SportFactory(name="Alpha Sport")
    names = list(Sport.objects.values_list("name", flat=True))
    assert names == sorted(names)


# ==================================================
# League — per-sport case-insensitive uniqueness
# ==================================================


def test_duplicate_league_name_within_same_sport_rejected():
    sport = SportFactory()
    LeagueFactory(sport=sport, name="Premier League")
    with pytest.raises(IntegrityError):
        LeagueFactory(sport=sport, name="Premier League")


def test_duplicate_league_name_case_insensitive_within_same_sport_rejected():
    sport = SportFactory()
    LeagueFactory(sport=sport, name="Premier League")
    with pytest.raises(IntegrityError):
        LeagueFactory(sport=sport, name="PREMIER LEAGUE")


def test_same_league_name_allowed_across_different_sports():
    LeagueFactory(sport=SportFactory(), name="Premier League")
    LeagueFactory(sport=SportFactory(), name="Premier League")


def test_league_str_includes_league_and_sport_name():
    sport = SportFactory(name="Football")
    league = LeagueFactory(sport=sport, name="Premier League")
    assert str(league) == "Premier League (Football)"


def test_leagues_cascade_delete_when_sport_deleted():
    sport = SportFactory()
    LeagueFactory(sport=sport)
    sport.delete()
    assert League.objects.count() == 0


# ==================================================
# Team — per-sport case-insensitive uniqueness
# ==================================================


def test_duplicate_team_name_within_same_sport_rejected():
    sport = SportFactory()
    TeamFactory(sport=sport, name="Arsenal")
    with pytest.raises(IntegrityError):
        TeamFactory(sport=sport, name="Arsenal")


def test_duplicate_team_name_case_insensitive_within_same_sport_rejected():
    sport = SportFactory()
    TeamFactory(sport=sport, name="Arsenal")
    with pytest.raises(IntegrityError):
        TeamFactory(sport=sport, name="ARSENAL")


def test_same_team_name_allowed_across_different_sports():
    TeamFactory(sport=SportFactory(), name="Arsenal")
    TeamFactory(sport=SportFactory(), name="Arsenal")


def test_team_str_returns_name():
    team = TeamFactory(name="Arsenal")
    assert str(team) == "Arsenal"


def test_teams_cascade_delete_when_sport_deleted():
    sport = SportFactory()
    TeamFactory(sport=sport)
    sport.delete()
    assert Team.objects.count() == 0
