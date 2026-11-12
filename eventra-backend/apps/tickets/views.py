from django.http import HttpResponse
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.bookings.models import Booking
from apps.common.permissions import IsOwnerOrAdmin
from apps.events.models import Event

from .models import Ticket
from .serializers import TicketCodeSerializer, TicketSerializer
from .services import (
    TicketAlreadyUsedError,
    TicketNotValidError,
    render_ticket_pdf,
    validate_ticket,
)

_TICKET_RELATED = (
    "event_seat",
    "event_seat__event",
    "event_seat__seat",
    "booking__user",
)


def _own_tickets(user):
    return Ticket.objects.filter(
        booking__user=user, booking__status__in=Booking.PAID_STATUSES
    ).select_related(*_TICKET_RELATED)


class TicketListView(generics.ListAPIView):
    serializer_class = TicketSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return _own_tickets(self.request.user)


class TicketDetailView(generics.RetrieveAPIView):
    serializer_class = TicketSerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = "id"
    lookup_url_kwarg = "id"

    def get_queryset(self):
        return _own_tickets(self.request.user)


class TicketDownloadView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_scope = "ticket-download"

    def get(self, request, id):
        ticket = generics.get_object_or_404(_own_tickets(request.user), id=id)
        if ticket.status != Ticket.Status.VALID:
            return Response(
                {"detail": "Only a valid ticket can be downloaded."},
                status=status.HTTP_409_CONFLICT,
            )
        pdf_bytes = render_ticket_pdf(ticket)
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = (
            f'attachment; filename="ticket-{ticket.ticket_code}.pdf"'
        )
        return response


class TicketCheckInView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrAdmin]
    owner_field = "organizer_id"
    throttle_scope = "ticket-check-in"

    def post(self, request, event_id):
        event = generics.get_object_or_404(Event.objects, pk=event_id)
        self.check_object_permissions(request, event)
        serializer = TicketCodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        ticket = Ticket.objects.filter(
            event_seat__event=event, ticket_code=serializer.validated_data["code"]
        ).first()
        if ticket is None:
            return Response(
                {"detail": "No ticket with this code for this event."},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            ticket = validate_ticket(ticket=ticket)
        except (TicketAlreadyUsedError, TicketNotValidError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)

        return Response(TicketSerializer(ticket).data, status=status.HTTP_201_CREATED)
