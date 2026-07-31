from .models import League, Sport, Team


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
