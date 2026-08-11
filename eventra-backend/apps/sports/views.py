import django_filters
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import mixins, status, viewsets
from rest_framework.response import Response
from apps.common.permissions import IsAdminForWrite
from .models import League, Sport, Team
from .serializers import LeagueSerializer, SportSerializer, TeamSerializer
from .services import (
    LeagueInUseError,
    LeagueSportReassignmentBlockedError,
    SportInUseError,
    TeamInUseError,
    TeamSportReassignmentBlockedError,
    ensure_league_deletable,
    ensure_league_sport_reassignable,
    ensure_sport_deletable,
    ensure_team_deletable,
    ensure_team_sport_reassignable,
)


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


class SportReassignmentGuardMixin:
    reassignment_guard = None
    reassignment_blocked_error = None

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)

        new_sport = serializer.validated_data.get("sport", instance.sport)
        try:
            self.reassignment_guard(instance, new_sport)
        except self.reassignment_blocked_error as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)

        self.perform_update(serializer)
        if getattr(instance, "_prefetched_objects_cache", None):
            instance._prefetched_objects_cache = {}
        return Response(serializer.data)


class SportViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    queryset = Sport.objects.all()
    serializer_class = SportSerializer
    permission_classes = [IsAdminForWrite]
    http_method_names = ["get", "post", "patch", "delete"]

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        try:
            ensure_sport_deletable(instance)
        except SportInUseError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return super().destroy(request, *args, **kwargs)


class LeagueViewSet(
    SportReassignmentGuardMixin,
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    queryset = League.objects.select_related("sport").all()
    serializer_class = LeagueSerializer
    permission_classes = [IsAdminForWrite]
    filter_backends = [DjangoFilterBackend]
    filterset_class = LeagueFilterSet
    http_method_names = ["get", "post", "patch", "delete"]
    reassignment_guard = staticmethod(ensure_league_sport_reassignable)
    reassignment_blocked_error = LeagueSportReassignmentBlockedError

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        try:
            ensure_league_deletable(instance)
        except LeagueInUseError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return super().destroy(request, *args, **kwargs)


class TeamViewSet(
    SportReassignmentGuardMixin,
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    queryset = Team.objects.select_related("sport").all()
    serializer_class = TeamSerializer
    permission_classes = [IsAdminForWrite]
    filter_backends = [DjangoFilterBackend]
    filterset_class = TeamFilterSet
    http_method_names = ["get", "post", "patch", "delete"]
    reassignment_guard = staticmethod(ensure_team_sport_reassignable)
    reassignment_blocked_error = TeamSportReassignmentBlockedError

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        try:
            ensure_team_deletable(instance)
        except TeamInUseError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return super().destroy(request, *args, **kwargs)
