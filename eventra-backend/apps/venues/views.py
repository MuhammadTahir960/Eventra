import django_filters
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.common.constants import Roles
from apps.common.mixins import SoftDeleteDestroyMixin, SoftDeleteRestoreMixin
from apps.common.permissions import IsAdmin, IsAdminForWrite, IsOrganizer
from apps.events.services import find_blocking_upcoming_event

from .models import Venue
from .serializers import BulkSeatTemplateSerializer, SeatSerializer, VenueSerializer
from .services import (
    CapacityExceededError,
    DuplicateSeatError,
    SeatTemplateExistsError,
    SeatTemplateInUseError,
    bulk_create_seat_template,
)


class VenueFilterSet(django_filters.FilterSet):
    city = django_filters.CharFilter(lookup_expr="iexact")

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
    filter_backends = [DjangoFilterBackend]
    filterset_class = VenueFilterSet
    http_method_names = ["get", "post", "patch", "delete"]

    def get_queryset(self):
        user = self.request.user
        include_inactive = str(
            self.request.query_params.get("include_inactive", "")
        ).lower() in ("1", "true", "yes")
        if (
            include_inactive
            and user
            and user.is_authenticated
            and user.role == Roles.ADMIN
        ):
            return Venue.all_objects.all()
        return Venue.objects.all()

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

    def perform_hard_delete_guard(self, instance):
        if find_blocking_upcoming_event(venue_id=instance.pk):
            return Response(
                {
                    "detail": (
                        "Cannot hard-delete: this venue is referenced by one "
                        "or more upcoming, non-cancelled events."
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
                allow_reseed=(request.user.role == Roles.ADMIN),
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
            return [(IsOrganizer | IsAdmin)()]

        if self.action == "restore":
            return [IsAdmin()]

        return super().get_permissions()
