from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.permissions import IsEventOwnerStrict
from apps.events.models import Event
from apps.events.services import get_visible_event_or_404

from .models import EventSeat
from .serializers import (
    EventSeatSerializer,
    InternalBroadcastRequestSerializer,
    SeatHoldRequestSerializer,
)
from .services import (
    AlreadyInstantiatedError,
    EmptySeatSelectionError,
    EventNotHoldableError,
    NotSeatedEventError,
    SeatLockConflictError,
    SeatsNotFoundError,
    SeatsUnavailableError,
    TooManySeatsError,
    UncoveredSectionsError,
    broadcast_seat_update,
    hold_seats,
    instantiate_event_seats,
)


class EventSeatListView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, event_id):
        event = get_visible_event_or_404(request.user, event_id)
        event_seats = EventSeat.objects.filter(event=event).select_related(
            "seat", "ticket_tier"
        )
        return Response(EventSeatSerializer(event_seats, many=True).data)


class EventSeatInstantiateView(APIView):
    permission_classes = [IsAuthenticated, IsEventOwnerStrict]

    def post(self, request, event_id):
        event = get_visible_event_or_404(request.user, event_id)
        self.check_object_permissions(request, event)

        try:
            created = instantiate_event_seats(event)
        except NotSeatedEventError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except UncoveredSectionsError as exc:
            return Response(
                {"detail": str(exc), "sections": exc.sections},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except AlreadyInstantiatedError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)

        return Response(
            EventSeatSerializer(created, many=True).data,
            status=status.HTTP_201_CREATED,
        )


class EventSeatHoldView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, event_id):
        event = get_visible_event_or_404(request.user, event_id)

        payload_serializer = SeatHoldRequestSerializer(data=request.data)
        payload_serializer.is_valid(raise_exception=True)

        try:
            group_id, expires_at, held_seats = hold_seats(
                event=event,
                seat_ids=payload_serializer.validated_data["seat_ids"],
                user=request.user,
            )
        except (EmptySeatSelectionError, TooManySeatsError, NotSeatedEventError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except SeatsNotFoundError as exc:
            return Response(
                {"detail": str(exc), "seat_ids": exc.seat_ids},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except EventNotHoldableError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except SeatsUnavailableError as exc:
            return Response(
                {"detail": str(exc), "seat_ids": exc.seat_ids},
                status=status.HTTP_409_CONFLICT,
            )
        except SeatLockConflictError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)

        return Response(
            {
                "hold_id": group_id,
                "expires_at": expires_at,
                "seats": EventSeatSerializer(held_seats, many=True).data,
            },
            status=status.HTTP_200_OK,
        )


class InternalSeatsBroadcastView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        payload = InternalBroadcastRequestSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        event = get_object_or_404(
            Event.objects.only("id", "slug"),
            slug=payload.validated_data["event_slug"],
        )

        seats = list(
            EventSeat.objects.filter(
                event=event, id__in=payload.validated_data["seat_ids"]
            ).select_related("seat", "ticket_tier")
        )
        if not seats:
            return Response(status=status.HTTP_204_NO_CONTENT)

        broadcast_seat_update(event=event, seats=seats)
        return Response(status=status.HTTP_204_NO_CONTENT)
