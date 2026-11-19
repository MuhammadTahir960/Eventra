import django_filters
from django.db import transaction
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_control
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.constants import Roles
from apps.common.mixins import SoftDeleteDestroyMixin, SoftDeleteRestoreMixin
from apps.common.permissions import IsAdmin, IsAdminForWrite, IsOrganizer, has_role

from .constants import COUNTRIES
from .models import Venue, VenueRequest
from .serializers import (
    BulkSeatTemplateSerializer,
    SeatSerializer,
    VenueRequestRejectionSerializer,
    VenueRequestSerializer,
    VenueSerializer,
)
from .services import (
    CapacityExceededError,
    DuplicateSeatError,
    SeatTemplateExistsError,
    SeatTemplateInUseError,
    VenueRequestNotPendingError,
    bulk_create_seat_template,
    fulfil_venue_request,
    reject_venue_request,
)


class CountryListView(APIView):
    permission_classes = [permissions.AllowAny]

    @method_decorator(cache_control(public=True, max_age=86400))
    def get(self, request):
        return Response(COUNTRIES)


class VenueFilterSet(django_filters.FilterSet):
    city = django_filters.CharFilter(lookup_expr="iexact", max_length=100)

    class Meta:
        model = Venue
        fields = ["city"]


class VenueViewSet(
    SoftDeleteDestroyMixin, SoftDeleteRestoreMixin, viewsets.ModelViewSet
):
    """
    Handles:
      GET    /venues/            -> list (filterable by city, case-insensitive)
      POST   /venues/            -> create (admin only)
      GET    /venues/{id}/       -> retrieve
      PATCH  /venues/{id}/       -> update (admin only)
      DELETE /venues/{id}/       -> soft-delete by default; ?hard=true for permanent (admin only)
      POST   /venues/{id}/restore/ -> reverse a soft-delete (admin only)
      GET    /venues/{id}/seats/ -> list this venue's seat template (organizer/admin)
      POST   /venues/{id}/seats/ -> bulk-create this venue's seat template (organizer/admin,
                                    first time only — admin required to re-seed afterward)
    """

    serializer_class = VenueSerializer
    permission_classes = [IsAdminForWrite]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    filter_backends = [DjangoFilterBackend]
    filterset_class = VenueFilterSet
    http_method_names = ["get", "post", "patch", "delete"]
    hard_delete_blocked_message = (
        "This venue has events, so it can't be deleted forever. It stays in the trash."
    )

    def get_queryset(self):
        if self.include_inactive():
            return Venue.all_objects.all()
        return Venue.objects.all()

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    def perform_restore_guard(self, instance):
        if Venue.objects.filter(
            name__iexact=instance.name, city__iexact=instance.city
        ).exists():
            return Response(
                {
                    "detail": (
                        "Cannot restore: an active venue with this name already exists in this city"
                    )
                },
                status=status.HTTP_409_CONFLICT,
            )
        return None

    @action(detail=True, methods=["get", "post"], url_path="seats")
    def seats(self, request, pk=None):
        venue = self.get_object()

        if request.method == "GET":
            seats = venue.seats.all()
            serializer = SeatSerializer(seats, many=True)
            return Response(serializer.data)

        payload_serializer = BulkSeatTemplateSerializer(data=request.data)
        payload_serializer.is_valid(raise_exception=True)

        try:
            created_seats = bulk_create_seat_template(
                venue=venue,
                sections=payload_serializer.validated_data["sections"],
                allow_reseed=has_role(request.user, Roles.ADMIN),
            )
        except SeatTemplateExistsError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except SeatTemplateInUseError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except CapacityExceededError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except DuplicateSeatError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)

        return Response(
            SeatSerializer(created_seats, many=True).data,
            status=status.HTTP_201_CREATED,
        )

    def get_permissions(self):
        if self.action == "seats":
            if self.request.method == "POST":
                return [permissions.IsAuthenticated(), IsAdmin()]
            return [(IsOrganizer | IsAdmin)()]

        if self.action == "restore":
            return [IsAdmin()]

        return super().get_permissions()


class VenueRequestListCreateView(generics.ListCreateAPIView):
    serializer_class = VenueRequestSerializer

    def get_permissions(self):
        if self.request.method == "POST":
            return [permissions.IsAuthenticated(), IsOrganizer()]
        return [permissions.IsAuthenticated()]

    def get_throttles(self):
        self.throttle_scope = "venue-request" if self.request.method == "POST" else None
        return super().get_throttles()

    def get_queryset(self):
        user = self.request.user
        queryset = VenueRequest.objects.all().order_by("created_at", "id")
        if user.role == Roles.ADMIN:
            return queryset
        return queryset.filter(requested_by=user)

    def perform_create(self, serializer):
        serializer.save(requested_by=self.request.user)


class VenueRequestRejectView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsAdmin]

    def post(self, request, request_id):
        venue_request = generics.get_object_or_404(VenueRequest, pk=request_id)
        payload = VenueRequestRejectionSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            reject_venue_request(venue_request, payload.validated_data["admin_notes"])
        except VenueRequestNotPendingError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(VenueRequestSerializer(venue_request).data)


class VenueRequestFulfilView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsAdmin]

    def post(self, request, request_id):
        venue_request = generics.get_object_or_404(VenueRequest, pk=request_id)
        try:
            fulfil_venue_request(venue_request)
        except VenueRequestNotPendingError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(VenueRequestSerializer(venue_request).data)
