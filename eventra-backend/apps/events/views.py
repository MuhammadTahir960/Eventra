import django_filters
from django.contrib.postgres.search import SearchQuery, SearchVector
from django.db import transaction
from django.db.models import Exists, OuterRef, Q
from django.utils import timezone
from rest_framework import generics, permissions, status, views, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotAuthenticated, PermissionDenied
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response

from apps.common.constants import Roles
from apps.common.mixins import SoftDeleteDestroyMixin, SoftDeleteRestoreMixin
from apps.common.permissions import (
    IsAdmin,
    IsEventOwnerStrict,
    IsOrganizer,
    IsOwnerOrAdmin,
    has_role,
)
from apps.payments.tasks import refund_event_bookings_task, retry_event_refunds_task
from apps.venues.models import COUNTRY_CHOICES

from .models import EVENT_SEARCH_CONFIG, Event, TicketTier
from .serializers import (
    EventSerializer,
    PendingEventSerializer,
    PostponementSerializer,
    RejectionSerializer,
    RunningLateSerializer,
    TicketTierSerializer,
    TierSectionMappingSerializer,
)
from .services import (
    DuplicateEventSlugError,
    EventEndNotExtendableError,
    EventHasPaidBookingsError,
    EventNotCancellableError,
    EventNotDeletableError,
    EventNotEditableError,
    EventNotPendingApprovalError,
    EventNotPostponableError,
    InvalidEventEndError,
    SeatMapLockedError,
    approve_event,
    cancel_event,
    ensure_can_restore_event,
    ensure_event_deletable,
    ensure_event_editable,
    ensure_sections_mappable,
    extend_event_end,
    lock_event,
    paid_bookings,
    postpone_event,
    reject_event,
    visible_events_for_ticket_holder,
    visible_events_for_user,
)


class EventFilterSet(django_filters.FilterSet):
    category = django_filters.UUIDFilter(field_name="category_id")
    city = django_filters.CharFilter(
        field_name="venue__city", lookup_expr="iexact", max_length=100
    )
    country = django_filters.ChoiceFilter(
        field_name="venue__country", choices=COUNTRY_CHOICES
    )
    status = django_filters.ChoiceFilter(choices=Event.Status.choices)
    date_from = django_filters.DateTimeFilter(
        field_name="start_datetime", lookup_expr="gte"
    )
    date_to = django_filters.DateTimeFilter(
        field_name="start_datetime", lookup_expr="lte"
    )
    search = django_filters.CharFilter(method="filter_search", max_length=100)
    is_active = django_filters.BooleanFilter()

    class Meta:
        model = Event
        fields = [
            "event_type",
            "category",
            "city",
            "country",
            "status",
            "date_from",
            "date_to",
            "search",
            "is_active",
        ]

    def filter_search(self, queryset, name, value):
        return queryset.annotate(
            search=SearchVector("title", "description", config=EVENT_SEARCH_CONFIG)
        ).filter(
            search=SearchQuery(
                value, config=EVENT_SEARCH_CONFIG, search_type="websearch"
            )
        )


def _save_locked(event, serializer, success_status, *checks):
    checks = (ensure_event_editable, *checks)
    try:
        for check in checks:
            check(event)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            lock_event(event)
            for check in checks:
                check(event)
            serializer.save()
    except (EventNotEditableError, SeatMapLockedError) as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
    return Response(serializer.data, status=success_status)


class EventViewSet(
    SoftDeleteDestroyMixin, SoftDeleteRestoreMixin, viewsets.ModelViewSet
):
    serializer_class = EventSerializer
    filterset_class = EventFilterSet
    permission_classes = [permissions.IsAuthenticated]
    owner_field = "organizer_id"
    http_method_names = ["get", "post", "patch", "delete"]
    throttle_scope = None
    include_inactive_roles = (Roles.ADMIN, Roles.ORGANIZER)
    hard_delete_blocked_message = (
        "This event has bookings, tickets or payouts, so it can't be deleted "
        "forever. It stays in the trash."
    )

    def get_trash_queryset(self):
        events = Event.all_objects.select_related(
            "venue", "category", "organizer", "league", "home_team", "away_team"
        )
        if has_role(self.request.user, Roles.ADMIN):
            return events
        return events.filter(organizer_id=self.request.user.id)

    def get_queryset(self):
        user = self.request.user
        if self.include_inactive():
            return (visible_events_for_user(user) | self.get_trash_queryset()).order_by(
                "-start_datetime", "id"
            )
        if self.action in ("retrieve", "ticket_tiers") and self.request.method == "GET":
            return visible_events_for_ticket_holder(user).order_by(
                "-start_datetime", "id"
            )
        return visible_events_for_user(user).order_by("-start_datetime", "id")

    def get_permissions(self):
        if self.action in ("list", "retrieve", "locations"):
            return [permissions.AllowAny()]
        if self.action == "create":
            return [permissions.IsAuthenticated(), (IsOrganizer | IsAdmin)()]
        if self.action in ("update", "partial_update"):
            return [permissions.IsAuthenticated(), IsEventOwnerStrict()]
        if self.action in (
            "destroy",
            "restore",
            "cancel",
            "extend_end",
            "postponements",
        ):
            return [permissions.IsAuthenticated(), IsOwnerOrAdmin()]
        return [perm() for perm in self.permission_classes]

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()

        with transaction.atomic():
            lock_event(instance)
            try:
                ensure_event_editable(instance)
            except EventNotEditableError as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)

            serializer = self.get_serializer(
                instance, data=request.data, partial=partial
            )
            serializer.is_valid(raise_exception=True)
            serializer.save()
        return Response(serializer.data)

    def perform_delete_guard(self, instance):
        try:
            ensure_event_deletable(instance)
        except EventNotDeletableError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return None

    def perform_restore_guard(self, instance):
        try:
            ensure_can_restore_event(instance)
        except DuplicateEventSlugError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return None

    @action(detail=False, methods=["get"], filterset_class=None, pagination_class=None)
    def locations(self, request):
        places = (
            visible_events_for_user(None)
            .filter(
                Q(status=Event.Status.COMPLETED) | Q(start_datetime__gt=timezone.now()),
                venue__isnull=False,
            )
            .values_list("venue__country", "venue__city")
            .distinct()
            .order_by("venue__country", "venue__city")
        )
        return Response(
            [{"country": country, "city": city} for country, city in places]
        )

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        event = self.get_object()

        with transaction.atomic():
            try:
                cancel_event(event, allow_completed=has_role(request.user, Roles.ADMIN))
            except EventNotCancellableError as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)

            transaction.on_commit(
                lambda: refund_event_bookings_task.delay(str(event.id)), robust=True
            )

        return Response(self.get_serializer(event).data)

    @action(detail=True, methods=["post"], throttle_scope="event-postpone")
    def postponements(self, request, pk=None):
        event = self.get_object()
        serializer = PostponementSerializer(data=request.data, context={"event": event})
        serializer.is_valid(raise_exception=True)
        try:
            postpone_event(
                event,
                serializer.validated_data["start_datetime"],
                serializer.validated_data["end_datetime"],
            )
        except EventNotPostponableError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(self.get_serializer(event).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="extend-end")
    def extend_end(self, request, pk=None):
        event = self.get_object()
        serializer = RunningLateSerializer(data=request.data, context={"event": event})
        serializer.is_valid(raise_exception=True)

        try:
            extend_event_end(event, serializer.validated_data["end_datetime"])
        except InvalidEventEndError as exc:
            return Response(
                {"end_datetime": [str(exc)]}, status=status.HTTP_400_BAD_REQUEST
            )
        except EventEndNotExtendableError as exc:
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
        serializer = TicketTierSerializer(
            data=request.data, context={"event": event, "request": request}
        )
        return _save_locked(event, serializer, status.HTTP_201_CREATED)

    @action(
        detail=True,
        methods=["patch"],
        url_path=r"ticket-tiers/(?P<tier_id>[^/.]+)",
        permission_classes=[permissions.IsAuthenticated, IsEventOwnerStrict],
    )
    def ticket_tier_update(self, request, pk=None, tier_id=None):
        event = self.get_object()
        tier = get_object_or_404(TicketTier, pk=tier_id, event=event)
        tier.event = event
        serializer = TicketTierSerializer(
            tier,
            data=request.data,
            partial=True,
            context={"event": event, "request": request},
        )
        return _save_locked(event, serializer, status.HTTP_200_OK)

    @action(
        detail=True,
        methods=["post"],
        url_path=r"ticket-tiers/(?P<tier_id>[^/.]+)/sections",
        permission_classes=[permissions.IsAuthenticated, IsEventOwnerStrict],
    )
    def ticket_tier_add_section(self, request, pk=None, tier_id=None):
        event = self.get_object()
        tier = get_object_or_404(TicketTier, pk=tier_id, event=event)
        tier.event = event
        serializer = TierSectionMappingSerializer(
            data=request.data, context={"event": event, "ticket_tier": tier}
        )
        return _save_locked(
            event, serializer, status.HTTP_201_CREATED, ensure_sections_mappable
        )


class EventRetryRefundsView(views.APIView):
    permission_classes = [permissions.IsAuthenticated, IsAdmin]

    def post(self, request, event_id):
        event = get_object_or_404(Event.all_objects, pk=event_id)
        retry_event_refunds_task.delay(str(event.id))

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
        payload = RejectionSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            reject_event(event, payload.validated_data["reason"])
        except (EventNotPendingApprovalError, EventHasPaidBookingsError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(EventSerializer(event, context={"request": request}).data)


class EventPendingListView(generics.ListAPIView):
    serializer_class = PendingEventSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdmin]

    def get_queryset(self):
        return (
            Event.objects.filter(status=Event.Status.PENDING_APPROVAL)
            .select_related("venue")
            .annotate(has_paid_bookings=Exists(paid_bookings(OuterRef("pk"))))
            .order_by("created_at")
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
