import pytest
from ..models import League, Team
from ..serializers import LeagueSerializer, SportSerializer, TeamSerializer
from ..factories import LeagueFactory, SportFactory, TeamFactory

pytestmark = pytest.mark.django_db


# ==================================================
# SportSerializer
# ==================================================


def test_valid_sport_payload_accepted():
    serializer = SportSerializer(data={"name": "Football"})
    assert serializer.is_valid(), serializer.errors
    sport = serializer.save()
    assert sport.name == "Football"


def test_blank_sport_name_rejected():
    serializer = SportSerializer(data={"name": "   "})
    assert serializer.is_valid() is False
    assert "name" in serializer.errors


def test_validate_name_blank_guard_is_defensive_but_unreachable_via_is_valid():
    from rest_framework import serializers as drf_serializers

    serializer = SportSerializer()
    with pytest.raises(drf_serializers.ValidationError, match="cannot be blank"):
        serializer.validate_name("   ")


def test_duplicate_sport_name_rejected():
    SportFactory(name="Football")
    serializer = SportSerializer(data={"name": "Football"})
    assert serializer.is_valid() is False
    assert "name" in serializer.errors


def test_duplicate_sport_name_case_insensitive_rejected():
    SportFactory(name="Football")
    serializer = SportSerializer(data={"name": "FOOTBALL"})
    assert serializer.is_valid() is False
    assert "name" in serializer.errors


def test_sport_name_is_stripped():
    serializer = SportSerializer(data={"name": "  Football  "})
    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["name"] == "Football"


def test_sport_race_condition_integrity_error_becomes_validation_error():
    SportFactory(name="Football")
    serializer = SportSerializer()
    with pytest.raises(Exception) as exc_info:
        serializer.create({"name": "Football"})
    from rest_framework import serializers as drf_serializers

    assert isinstance(exc_info.value, drf_serializers.ValidationError)


# ==================================================
# LeagueSerializer
# ==================================================


def test_valid_league_payload_accepted():
    sport = SportFactory()
    serializer = LeagueSerializer(data={"sport": sport.pk, "name": "Premier League"})
    assert serializer.is_valid(), serializer.errors
    league = serializer.save()
    assert league.name == "Premier League"


def test_blank_league_name_rejected():
    sport = SportFactory()
    serializer = LeagueSerializer(data={"sport": sport.pk, "name": "   "})
    assert serializer.is_valid() is False
    assert "name" in serializer.errors


def test_scoped_unique_name_mixin_blank_guard_is_defensive_but_unreachable_via_is_valid():
    from rest_framework import serializers as drf_serializers

    sport = SportFactory()
    serializer = LeagueSerializer()
    with pytest.raises(drf_serializers.ValidationError, match="cannot be blank"):
        serializer.validate({"sport": sport, "name": "   "})


def test_duplicate_league_name_within_sport_rejected():
    sport = SportFactory()
    LeagueFactory(sport=sport, name="Premier League")
    serializer = LeagueSerializer(data={"sport": sport.pk, "name": "Premier League"})
    assert serializer.is_valid() is False
    assert "name" in serializer.errors


def test_same_league_name_in_different_sport_accepted():
    LeagueFactory(sport=SportFactory(), name="Premier League")
    other_sport = SportFactory()
    serializer = LeagueSerializer(
        data={"sport": other_sport.pk, "name": "Premier League"}
    )
    assert serializer.is_valid(), serializer.errors


def test_league_missing_sport_rejected():
    serializer = LeagueSerializer(data={"name": "Premier League"})
    assert serializer.is_valid() is False
    assert "sport" in serializer.errors


def test_league_race_condition_integrity_error_becomes_validation_error():
    sport = SportFactory()
    LeagueFactory(sport=sport, name="Premier League")
    serializer = LeagueSerializer()
    with pytest.raises(Exception) as exc_info:
        serializer.create({"sport": sport, "name": "Premier League"})
    from rest_framework import serializers as drf_serializers

    assert isinstance(exc_info.value, drf_serializers.ValidationError)
    assert League.objects.filter(sport=sport, name="Premier League").count() == 1


# ==================================================
# TeamSerializer
# ==================================================


def test_valid_team_payload_accepted():
    sport = SportFactory()
    serializer = TeamSerializer(data={"sport": sport.pk, "name": "Arsenal"})
    assert serializer.is_valid(), serializer.errors
    team = serializer.save()
    assert team.name == "Arsenal"


def test_blank_team_name_rejected():
    sport = SportFactory()
    serializer = TeamSerializer(data={"sport": sport.pk, "name": "   "})
    assert serializer.is_valid() is False
    assert "name" in serializer.errors


def test_duplicate_team_name_within_sport_rejected():
    sport = SportFactory()
    TeamFactory(sport=sport, name="Arsenal")
    serializer = TeamSerializer(data={"sport": sport.pk, "name": "Arsenal"})
    assert serializer.is_valid() is False
    assert "name" in serializer.errors


def test_same_team_name_in_different_sport_accepted():
    TeamFactory(sport=SportFactory(), name="Arsenal")
    other_sport = SportFactory()
    serializer = TeamSerializer(data={"sport": other_sport.pk, "name": "Arsenal"})
    assert serializer.is_valid(), serializer.errors


def test_team_missing_sport_rejected():
    serializer = TeamSerializer(data={"name": "Arsenal"})
    assert serializer.is_valid() is False
    assert "sport" in serializer.errors


def test_team_race_condition_integrity_error_becomes_validation_error():
    sport = SportFactory()
    TeamFactory(sport=sport, name="Arsenal")
    serializer = TeamSerializer()
    with pytest.raises(Exception) as exc_info:
        serializer.create({"sport": sport, "name": "Arsenal"})
    from rest_framework import serializers as drf_serializers

    assert isinstance(exc_info.value, drf_serializers.ValidationError)
    assert Team.objects.filter(sport=sport, name="Arsenal").count() == 1
