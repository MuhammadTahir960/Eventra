from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.permissions import IsAdmin, IsEventOwnerStrict, IsOrganizer
from apps.events.models import Event

from .models import OrganizerPayout
from .serializers import EventSalesSerializer, OrganizerPayoutSerializer
from .services import (
    PayoutNotSettleableError,
    get_event_sales,
    request_payout_settlement,
)


class OrganizerEventSalesView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsEventOwnerStrict]

    def get(self, request, event_id):
        event = generics.get_object_or_404(Event.all_objects, pk=event_id)
        self.check_object_permissions(request, event)

        sales = get_event_sales(event)
        return Response(EventSalesSerializer(sales).data)


class OrganizerPayoutListView(generics.ListAPIView):
    serializer_class = OrganizerPayoutSerializer
    permission_classes = [permissions.IsAuthenticated, IsOrganizer]

    def get_queryset(self):
        return OrganizerPayout.objects.filter(
            event__organizer_id=self.request.user.id
        ).select_related("event")


class AdminPayoutListView(generics.ListAPIView):
    serializer_class = OrganizerPayoutSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdmin]
    filterset_fields = ["status"]

    def get_queryset(self):
        return OrganizerPayout.objects.select_related("event").all()


class AdminPayoutSettleView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsAdmin]

    def post(self, request, payout_id):
        payout = generics.get_object_or_404(OrganizerPayout, pk=payout_id)

        try:
            payout = request_payout_settlement(payout)
        except PayoutNotSettleableError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)

        return Response(
            OrganizerPayoutSerializer(payout).data, status=status.HTTP_202_ACCEPTED
        )
