import django_filters
from django.contrib.postgres.search import SearchQuery, SearchVector
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotAuthenticated, PermissionDenied
from rest_framework.response import Response
from apps.common.constants import Roles
from apps.common.mixins import SoftDeleteRestoreMixin
from apps.common.permissions import IsAdmin, IsOrganizer
from .models import Event, EVENT_SEARCH_CONFIG, TicketTier
from .permissions import IsEventOwnerOrAdminForDelete, IsEventOwnerStrict
from .serializers import (
    EventSerializer,
    TicketTierSerializer,
    TierSectionMappingSerializer,
)
from .services import (
    DuplicateEventSlugError,
    EventNotDeletableError,
    EventNotPendingApprovalError,
    TierPriceImmutableError,
    approve_event,
    ensure_can_restore_event,
    ensure_event_deletable,
    reject_event,
)


class EventFilterSet(django_filters.FilterSet):
    category = django_filters.UUIDFilter(field_name="category_id")
    city = django_filters.CharFilter(field_name="venue__city", lookup_expr="iexact")
    date_from = django_filters.DateTimeFilter(
        field_name="start_datetime", lookup_expr="gte"
    )
    date_to = django_filters.DateTimeFilter(
        field_name="start_datetime", lookup_expr="lte"
    )
    min_price = django_filters.NumberFilter(
        field_name="ticket_tiers__price", lookup_expr="gte", distinct=True
    )
    max_price = django_filters.NumberFilter(
        field_name="ticket_tiers__price", lookup_expr="lte", distinct=True
    )
    search = django_filters.CharFilter(method="filter_search")

    class Meta:
        model = Event
        fields = [
            "event_type",
            "category",
            "city",
            "date_from",
            "date_to",
            "min_price",
            "max_price",
            "search",
        ]

    def filter_search(self, queryset, name, value):
        return queryset.annotate(
            search=SearchVector("title", "description", config=EVENT_SEARCH_CONFIG)
        ).filter(
            search=SearchQuery(
                value, config=EVENT_SEARCH_CONFIG, search_type="websearch"
            )
        )


class EventViewSet(SoftDeleteRestoreMixin, viewsets.ModelViewSet):
    serializer_class = EventSerializer
    filterset_class = EventFilterSet
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ["get", "post", "patch", "delete"]

    def get_queryset(self):
        user = self.request.user
        qs = Event.objects.select_related(
            "venue", "category", "organizer", "league", "home_team", "away_team"
        )
        public_statuses = [Event.Status.APPROVED, Event.Status.COMPLETED]

        if not user or not user.is_authenticated:
            return qs.filter(status__in=public_statuses)

        include_inactive = str(
            self.request.query_params.get("include_inactive", "")
        ).lower() in ("1", "true", "yes")
        if user.role == Roles.ADMIN:
            if include_inactive:
                qs = Event.all_objects.select_related(
                    "venue", "category", "organizer", "league", "home_team", "away_team"
                )
            return qs
        if user.role == Roles.ORGANIZER:
            return qs.filter(Q(organizer=user) | Q(status__in=public_statuses))
        return qs.filter(status__in=public_statuses)

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [permissions.AllowAny()]
        if self.action == "create":
            return [permissions.IsAuthenticated(), (IsOrganizer | IsAdmin)()]
        if self.action in ("update", "partial_update"):
            return [permissions.IsAuthenticated(), IsEventOwnerStrict()]
        if self.action == "destroy":
            return [permissions.IsAuthenticated(), IsEventOwnerOrAdminForDelete()]
        if self.action == "restore":
            return [IsAdmin()]
        if self.action in ("approve", "reject"):
            return [permissions.IsAuthenticated(), IsAdmin()]
        return [perm() for perm in self.permission_classes]

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()

        if instance.status == Event.Status.COMPLETED:
            return Response(
                {"detail": "Event is completed and can no longer be edited."},
                status=status.HTTP_409_CONFLICT,
            )

        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()

        try:
            ensure_event_deletable(instance)
        except EventNotDeletableError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)

        hard = str(request.query_params.get("hard", "")).lower() in ("1", "true", "yes")
        if not hard:
            instance.is_active = False
            instance.save(update_fields=["is_active", "updated_at"])
            return Response(status=status.HTTP_204_NO_CONTENT)

        instance.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    def perform_restore_guard(self, instance):
        try:
            ensure_can_restore_event(instance)
        except DuplicateEventSlugError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return None

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        """Admin-only: pending_approval -> approved."""
        event = self.get_object()
        try:
            approve_event(event)
        except EventNotPendingApprovalError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(self.get_serializer(event).data)

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        """Admin-only: pending_approval -> rejected."""
        event = self.get_object()
        try:
            reject_event(event)
        except EventNotPendingApprovalError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(self.get_serializer(event).data)

    @action(
        detail=True,
        methods=["get", "post"],
        url_path="ticket-tiers",
        permission_classes=[permissions.AllowAny],
    )
    def ticket_tiers(self, request, pk=None):
        event = self.get_object()

        if request.method == "GET":
            tiers = event.ticket_tiers.all()
            return Response(TicketTierSerializer(tiers, many=True).data)

        if not (request.user and request.user.is_authenticated):
            raise NotAuthenticated()
        if not IsEventOwnerStrict().has_object_permission(request, self, event):
            raise PermissionDenied("Only the event's owner may add ticket tiers.")
        if event.status == Event.Status.COMPLETED:
            return Response(
                {"detail": "Event is completed."}, status=status.HTTP_409_CONFLICT
            )

        serializer = TicketTierSerializer(
            data=request.data, context={"event": event, "request": request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(
        detail=True,
        methods=["patch"],
        url_path=r"ticket-tiers/(?P<tier_id>[^/.]+)",
        permission_classes=[permissions.IsAuthenticated, IsEventOwnerStrict],
    )
    def ticket_tier_update(self, request, pk=None, tier_id=None):
        event = self.get_object()
        tier = get_object_or_404(TicketTier, pk=tier_id, event=event)

        if event.status == Event.Status.COMPLETED:
            return Response(
                {"detail": "Event is completed."}, status=status.HTTP_409_CONFLICT
            )

        serializer = TicketTierSerializer(
            tier,
            data=request.data,
            partial=True,
            context={"event": event, "request": request},
        )
        serializer.is_valid(raise_exception=True)

        try:
            serializer.save()
        except TierPriceImmutableError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)

        return Response(serializer.data)

    @action(
        detail=True,
        methods=["post"],
        url_path=r"ticket-tiers/(?P<tier_id>[^/.]+)/sections",
        permission_classes=[permissions.IsAuthenticated, IsEventOwnerStrict],
    )
    def ticket_tier_add_section(self, request, pk=None, tier_id=None):
        event = self.get_object()
        tier = get_object_or_404(TicketTier, pk=tier_id, event=event)

        if event.status == Event.Status.COMPLETED:
            return Response(
                {"detail": "Event is completed."}, status=status.HTTP_409_CONFLICT
            )

        serializer = TierSectionMappingSerializer(
            data=request.data, context={"event": event, "ticket_tier": tier}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
