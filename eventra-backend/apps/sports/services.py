from django.db.models import Q
from apps.events.models import Event
from .models import League, Sport, Team


class SportInUseError(Exception):
    """
    Raised when a Sport can't be deleted because a League/Team under it
    is referenced by an event.
    """


class LeagueInUseError(Exception):
    """Raised when a League can't be deleted because it's referenced by an event."""


class TeamInUseError(Exception):
    """
    Raised when a Team can't be deleted because it's referenced (as home
    or away team) by an event.
    """


class LeagueSportReassignmentBlockedError(Exception):
    """
    Raised when a League's `sport` is being changed while an event still
    references it.
    """


class TeamSportReassignmentBlockedError(Exception):
    """
    Raised when a Team's `sport` is being changed while an event still
    references it as home_team or away_team.
    """


def ensure_sport_deletable(sport: Sport) -> None:
    blocking = Event.all_objects.filter(
        Q(league__sport=sport) | Q(home_team__sport=sport) | Q(away_team__sport=sport)
    )
    if blocking.exists():
        raise SportInUseError(
            "Cannot delete: one or more events reference a league or team "
            "under this sport."
        )


def ensure_league_deletable(league: League) -> None:
    if Event.all_objects.filter(league=league).exists():
        raise LeagueInUseError(
            "Cannot delete: one or more events reference this league."
        )


def ensure_team_deletable(team: Team) -> None:
    blocking = Event.all_objects.filter(Q(home_team=team) | Q(away_team=team))
    if blocking.exists():
        raise TeamInUseError("Cannot delete: one or more events reference this team.")


def ensure_league_sport_reassignable(league: League, new_sport: Sport) -> None:
    if league.sport_id == new_sport.id:
        return

    if Event.all_objects.filter(league=league).exists():
        raise LeagueSportReassignmentBlockedError(
            "Cannot change sport: one or more events reference this league."
        )


def ensure_team_sport_reassignable(team: Team, new_sport: Sport) -> None:
    if team.sport_id == new_sport.id:
        return

    blocking = Event.all_objects.filter(Q(home_team=team) | Q(away_team=team))
    if blocking.exists():
        raise TeamSportReassignmentBlockedError(
            "Cannot change sport: one or more events reference this team."
        )


class DuplicateSportError(Exception):
    """Raised when a Sport with the same name (case-insensitive) already exists."""


class DuplicateLeagueError(Exception):
    """Raised when a League with the same name already exists for that Sport."""


class DuplicateTeamError(Exception):
    """Raised when a Team with the same name already exists for that Sport."""


def ensure_unique_sport_name(name: str, *, exclude_pk=None) -> None:
    qs = Sport.objects.filter(name__iexact=name)
    if exclude_pk is not None:
        qs = qs.exclude(pk=exclude_pk)
    if qs.exists():
        raise DuplicateSportError("A sport with this name already exists.")


def ensure_unique_league_name(sport: Sport, name: str, *, exclude_pk=None) -> None:
    qs = League.objects.filter(sport=sport, name__iexact=name)
    if exclude_pk is not None:
        qs = qs.exclude(pk=exclude_pk)
    if qs.exists():
        raise DuplicateLeagueError(
            "A league with this name already exists for this sport."
        )


def ensure_unique_team_name(sport: Sport, name: str, *, exclude_pk=None) -> None:
    qs = Team.objects.filter(sport=sport, name__iexact=name)
    if exclude_pk is not None:
        qs = qs.exclude(pk=exclude_pk)
    if qs.exists():
        raise DuplicateTeamError("A team with this name already exists for this sport.")
