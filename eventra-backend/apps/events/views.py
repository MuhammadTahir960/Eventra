import django_filters
from django.contrib.postgres.search import SearchQuery, SearchVector
from django.db import transaction
from django.db.models import ProtectedError
from rest_framework import generics, permissions, status, views, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotAuthenticated, PermissionDenied
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response

from apps.common.constants import Roles
from apps.common.mixins import SoftDeleteRestoreMixin
from apps.common.permissions import IsAdmin, IsEventOwnerStrict, IsOrganizer
from apps.payments.tasks import refund_event_bookings_task

from .models import EVENT_SEARCH_CONFIG, Event, TicketTier
from .permissions import IsEventOwnerOrAdminForDelete
from .serializers import (
    EventSerializer,
    TicketTierSerializer,
    TierSectionMappingSerializer,
)
from .services import (
    DuplicateEventSlugError,
    EventNotCancellableError,
    EventNotDeletableError,
    EventNotEditableError,
    EventNotPendingApprovalError,
    EventRejectionReasonRequiredError,
    TierPriceImmutableError,
    approve_event,
    cancel_event,
    ensure_can_restore_event,
    ensure_event_deletable,
    ensure_event_editable,
    reject_event,
    visible_events_for_user,
)


class EventFilterSet(django_filters.FilterSet):
    category = django_filters.UUIDFilter(field_name="category_id")
    city = django_filters.CharFilter(field_name="venue__city", lookup_expr="iexact")
    status = django_filters.ChoiceFilter(choices=Event.Status.choices)
    date_from = django_filters.DateTimeFilter(
        field_name="start_datetime", lookup_expr="gte"
    )
    date_to = django_filters.DateTimeFilter(
        field_name="start_datetime", lookup_expr="lte"
    )
    min_price = django_filters.NumberFilter(method="filter_noop")
    max_price = django_filters.NumberFilter(method="filter_noop")
    search = django_filters.CharFilter(method="filter_search")

    class Meta:
        model = Event
        fields = [
            "event_type",
            "category",
            "city",
            "status",
            "date_from",
            "date_to",
            "min_price",
            "max_price",
            "search",
        ]

    def filter_noop(self, queryset, name, value):
        return queryset

    def filter_queryset(self, queryset):
        queryset = super().filter_queryset(queryset)
        bounds = {}
        if self.form.cleaned_data.get("min_price") is not None:
            bounds["ticket_tiers__price__gte"] = self.form.cleaned_data["min_price"]
        if self.form.cleaned_data.get("max_price") is not None:
            bounds["ticket_tiers__price__lte"] = self.form.cleaned_data["max_price"]
        if bounds:
            queryset = queryset.filter(**bounds).distinct()
        return queryset

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
        include_inactive = str(
            self.request.query_params.get("include_inactive", "")
        ).lower() in ("1", "true", "yes")

        if (
            user
            and user.is_authenticated
            and user.role == Roles.ADMIN
            and include_inactive
        ):
            return Event.all_objects.select_related(
                "venue", "category", "organizer", "league", "home_team", "away_team"
            ).order_by("-start_datetime", "id")
        return visible_events_for_user(user).order_by("-start_datetime", "id")

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [permissions.AllowAny()]
        if self.action == "create":
            return [permissions.IsAuthenticated(), (IsOrganizer | IsAdmin)()]
        if self.action in ("update", "partial_update"):
            return [permissions.IsAuthenticated(), IsEventOwnerStrict()]
        if self.action == "destroy":
            return [permissions.IsAuthenticated(), IsEventOwnerOrAdminForDelete()]
        if self.action == "cancel":
            return [permissions.IsAuthenticated(), IsEventOwnerOrAdminForDelete()]
        if self.action == "restore":
            return [IsAdmin()]
        return [perm() for perm in self.permission_classes]

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()

        try:
            ensure_event_editable(instance)
        except EventNotEditableError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)

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

        try:
            with transaction.atomic():
                instance.delete()
        except ProtectedError:
            return Response(
                {
                    "detail": "Cannot permanently delete an event that has "
                    "bookings, tickets or payouts. Soft-delete it instead."
                },
                status=status.HTTP_409_CONFLICT,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)

    def perform_restore_guard(self, instance):
        try:
            ensure_can_restore_event(instance)
        except DuplicateEventSlugError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return None

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        event = self.get_object()

        with transaction.atomic():
            try:
                cancel_event(event)
            except EventNotCancellableError as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)

            transaction.on_commit(
                lambda: refund_event_bookings_task.delay(str(event.id)), robust=True
            )

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
        try:
            ensure_event_editable(event)
        except EventNotEditableError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)

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

        try:
            ensure_event_editable(event)
        except EventNotEditableError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)

        serializer = TicketTierSerializer(
            tier,
            data=request.data,
            partial=True,
            context={"event": event, "request": request},
        )
        serializer.is_valid(raise_exception=True)

        try:
            with transaction.atomic():
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

        try:
            ensure_event_editable(event)
        except EventNotEditableError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)

        serializer = TierSectionMappingSerializer(
            data=request.data, context={"event": event, "ticket_tier": tier}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class EventRetryRefundsView(views.APIView):
    permission_classes = [permissions.IsAuthenticated, IsAdmin]

    def post(self, request, event_id):
        event = get_object_or_404(Event.all_objects, pk=event_id)

        if event.status != Event.Status.CANCELLED:
            return Response(
                {"detail": "Retrying refunds only makes sense for a cancelled event."},
                status=status.HTTP_409_CONFLICT,
            )

        refund_event_bookings_task.delay(str(event.id), retry_failed=True)

        return Response(status=status.HTTP_202_ACCEPTED)


class EventApproveView(views.APIView):
    permission_classes = [permissions.IsAuthenticated, IsAdmin]

    def post(self, request, event_id):
        event = get_object_or_404(Event.objects, pk=event_id)
        try:
            approve_event(event)
        except EventNotPendingApprovalError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(EventSerializer(event, context={"request": request}).data)


class EventRejectView(views.APIView):
    permission_classes = [permissions.IsAuthenticated, IsAdmin]

    def post(self, request, event_id):
        event = get_object_or_404(Event.objects, pk=event_id)
        try:
            reason = (
                request.data.get("reason") if hasattr(request.data, "get") else None
            )
            reject_event(event, reason if isinstance(reason, str) else "")
        except EventNotPendingApprovalError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except EventRejectionReasonRequiredError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(EventSerializer(event, context={"request": request}).data)


class EventPendingListView(generics.ListAPIView):
    serializer_class = EventSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdmin]

    def get_queryset(self):
        return Event.objects.filter(status=Event.Status.PENDING_APPROVAL).order_by(
            "created_at"
        )


class OrganizerEventListView(generics.ListAPIView):
    serializer_class = EventSerializer
    permission_classes = [permissions.IsAuthenticated, IsOrganizer]

    def get_queryset(self):
        return (
            Event.objects.filter(organizer=self.request.user)
            .select_related(
                "venue", "category", "organizer", "league", "home_team", "away_team"
            )
            .order_by("-created_at", "id")
        )
