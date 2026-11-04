from django.http import HttpResponse
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.bookings.models import Booking

from .models import Ticket
from .permissions import IsTicketEventOwnerOrAdmin
from .serializers import TicketSerializer
from .services import (
    TicketAlreadyUsedError,
    TicketNotValidError,
    TicketWrongEventError,
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
        pdf_bytes = render_ticket_pdf(ticket)
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = (
            f'attachment; filename="ticket-{ticket.ticket_code}.pdf"'
        )
        return response


class TicketValidateView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsTicketEventOwnerOrAdmin]

    def post(self, request, event_id, ticket_id):
        ticket = generics.get_object_or_404(
            Ticket.objects.select_related(*_TICKET_RELATED), id=ticket_id
        )
        self.check_object_permissions(request, ticket)

        try:
            ticket = validate_ticket(ticket=ticket, event_id=event_id)
        except TicketWrongEventError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except TicketAlreadyUsedError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except TicketNotValidError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)

        return Response(TicketSerializer(ticket).data, status=status.HTTP_200_OK)
