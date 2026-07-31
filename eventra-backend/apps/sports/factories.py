import factory
from .models import League, Sport, Team


class SportFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Sport

    name = factory.Sequence(lambda n: f"Sport {n}")


class LeagueFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = League

    sport = factory.SubFactory(SportFactory)
    name = factory.Sequence(lambda n: f"League {n}")


class TeamFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Team

    sport = factory.SubFactory(SportFactory)
    name = factory.Sequence(lambda n: f"Team {n}")
