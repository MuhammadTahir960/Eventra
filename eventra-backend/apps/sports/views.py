import django_filters
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import mixins, viewsets
from apps.common.permissions import IsAdminForWrite
from .models import League, Sport, Team
from .serializers import LeagueSerializer, SportSerializer, TeamSerializer


class SportRelatedFilterSet(django_filters.FilterSet):
    sport = django_filters.UUIDFilter(field_name="sport_id")


class LeagueFilterSet(SportRelatedFilterSet):
    class Meta:
        model = League
        fields = ["sport"]


class TeamFilterSet(SportRelatedFilterSet):
    class Meta:
        model = Team
        fields = ["sport"]


class SportViewSet(
    mixins.ListModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet
):
    queryset = Sport.objects.all()
    serializer_class = SportSerializer
    permission_classes = [IsAdminForWrite]


class LeagueViewSet(
    mixins.ListModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet
):
    queryset = League.objects.select_related("sport").all()
    serializer_class = LeagueSerializer
    permission_classes = [IsAdminForWrite]
    filter_backends = [DjangoFilterBackend]
    filterset_class = LeagueFilterSet


class TeamViewSet(
    mixins.ListModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet
):
    queryset = Team.objects.select_related("sport").all()
    serializer_class = TeamSerializer
    permission_classes = [IsAdminForWrite]
    filter_backends = [DjangoFilterBackend]
    filterset_class = TeamFilterSet
