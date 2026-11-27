from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.permissions import IsAdmin, IsEventOwnerStrict, IsOrganizer
from apps.events.models import Event

from . import account_numbers
from .models import OrganizerPayout, Partner
from .serializers import (
    AwaitingPayoutSerializer,
    EventSalesSerializer,
    OrganizerPayoutSerializer,
    PartnerSerializer,
)
from .services import (
    PAYEE_RELATED,
    PayoutNotAvailableError,
    PayoutNotSettleableError,
    awaiting_payout,
    get_event_sales,
    pay_out_event,
    request_payout_settlement,
)

_PAYOUT_RELATED = ("event__venue", *(f"event__{path}" for path in PAYEE_RELATED))


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
        ).select_related(*_PAYOUT_RELATED)


class AdminPayoutListView(generics.ListAPIView):
    serializer_class = OrganizerPayoutSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdmin]
    filterset_fields = ["status"]

    def get_queryset(self):
        return OrganizerPayout.objects.select_related(*_PAYOUT_RELATED)


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


class AdminPayoutReadyListView(generics.ListAPIView):
    serializer_class = AwaitingPayoutSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdmin]

    def get_queryset(self):
        return awaiting_payout(Event.all_objects.all())


class OrganizerPayoutUpcomingListView(generics.ListAPIView):
    serializer_class = AwaitingPayoutSerializer
    permission_classes = [permissions.IsAuthenticated, IsOrganizer]

    def get_queryset(self):
        return awaiting_payout(
            Event.all_objects.filter(organizer_id=self.request.user.id)
        )


class AdminEventPayOutView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsAdmin]

    def post(self, request, event_id):
        event = generics.get_object_or_404(Event.all_objects, pk=event_id)

        try:
            payout = pay_out_event(event)
        except PayoutNotAvailableError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)

        return Response(
            OrganizerPayoutSerializer(payout).data, status=status.HTTP_201_CREATED
        )


class PayoutAccountNumberView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_scope = "payout-account-number"

    def post(self, request):
        return Response(account_numbers.issue(), status=status.HTTP_201_CREATED)


class AdminPartnerListView(generics.ListAPIView):
    serializer_class = PartnerSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdmin]
    pagination_class = None

    def get_queryset(self):
        return Partner.objects.payable()
