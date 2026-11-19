from django.utils import timezone
from rest_framework import serializers

from .models import OrganizerPayout
from .services import payout_available_at, split_gross_revenue


class OrganizerPayoutSerializer(serializers.ModelSerializer):
    event_id = serializers.UUIDField(source="event.id", read_only=True)
    event_title = serializers.CharField(source="event.title", read_only=True)
    currency = serializers.CharField(source="event.currency", read_only=True)
    net_amount = serializers.DecimalField(
        max_digits=18, decimal_places=2, read_only=True
    )

    class Meta:
        model = OrganizerPayout
        fields = [
            "id",
            "event_id",
            "event_title",
            "currency",
            "gross_revenue",
            "platform_fee",
            "net_amount",
            "status",
            "settled_at",
            "created_at",
        ]
        read_only_fields = fields


class TicketSaleSerializer(serializers.Serializer):
    ticket_id = serializers.UUIDField(read_only=True)
    ticket_code = serializers.CharField(read_only=True)
    amount = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    refunded = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    status = serializers.ChoiceField(choices=["confirmed", "refunded"], read_only=True)


class EventSalesSerializer(serializers.Serializer):
    currency = serializers.CharField(read_only=True)
    tickets_sold = serializers.IntegerField(read_only=True)
    gross_revenue = serializers.DecimalField(
        max_digits=18, decimal_places=2, read_only=True
    )
    tickets = TicketSaleSerializer(many=True, read_only=True)


class AwaitingPayoutSerializer(serializers.Serializer):
    def to_representation(self, event):
        gross, fee, net = split_gross_revenue(event.gross_revenue)
        available_at = payout_available_at(event)
        organizer = event.organizer
        return {
            "event_id": str(event.id),
            "event_title": event.title,
            "organizer_name": str(organizer).strip() or organizer.email,
            "venue_name": event.venue.name if event.venue else "",
            "currency": event.currency,
            "completed_at": serializers.DateTimeField().to_representation(
                event.completed_at
            ),
            "payout_available_at": serializers.DateTimeField().to_representation(
                available_at
            ),
            "eligible": timezone.now() >= available_at,
            "gross_revenue": str(gross),
            "platform_fee": str(fee),
            "net_amount": str(net),
        }
