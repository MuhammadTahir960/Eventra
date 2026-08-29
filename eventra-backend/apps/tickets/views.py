from django.http import HttpResponse
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Ticket
from .permissions import IsTicketEventOwnerStrict
from .serializers import TicketSerializer
from .services import (
    TicketAlreadyCancelledError,
    TicketAlreadyUsedError,
    TicketWrongEventError,
    render_ticket_pdf,
    validate_ticket,
)

_TICKET_RELATED = ("event_seat", "event_seat__event", "event_seat__seat", "booking")


class TicketListView(generics.ListAPIView):
    serializer_class = TicketSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Ticket.objects.filter(booking__user=self.request.user).select_related(
            *_TICKET_RELATED
        )


class TicketDetailView(generics.RetrieveAPIView):
    serializer_class = TicketSerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = "id"
    lookup_url_kwarg = "id"

    def get_queryset(self):
        return Ticket.objects.filter(booking__user=self.request.user).select_related(
            *_TICKET_RELATED
        )


class TicketDownloadView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, id):
        ticket = generics.get_object_or_404(
            Ticket.objects.filter(booking__user=request.user).select_related(
                *_TICKET_RELATED
            ),
            id=id,
        )
        pdf_bytes = render_ticket_pdf(ticket)
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = (
            f'attachment; filename="ticket-{ticket.ticket_code}.pdf"'
        )
        return response


class TicketValidateView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsTicketEventOwnerStrict]

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
        except TicketAlreadyCancelledError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)

        return Response(TicketSerializer(ticket).data, status=status.HTTP_200_OK)
