from django.utils import timezone
from rest_framework import serializers

from .models import OrganizerPayout
from .services import compute_payout_amounts, payout_available_at


class OrganizerPayoutSerializer(serializers.ModelSerializer):
    event_id = serializers.UUIDField(source="event.id", read_only=True)
    event_title = serializers.CharField(source="event.title", read_only=True)

    class Meta:
        model = OrganizerPayout
        fields = [
            "id",
            "event_id",
            "event_title",
            "gross_revenue",
            "platform_fee",
            "net_amount",
            "status",
            "payout_reference",
            "period_start",
            "period_end",
            "settled_at",
            "created_at",
        ]
        read_only_fields = fields


class TicketSaleSerializer(serializers.Serializer):
    ticket_id = serializers.UUIDField()
    ticket_code = serializers.CharField()
    amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    status = serializers.ChoiceField(choices=["confirmed", "refunded"])


class EventSalesSerializer(serializers.Serializer):
    tickets_sold = serializers.IntegerField()
    gross_revenue = serializers.DecimalField(max_digits=10, decimal_places=2)
    tickets = TicketSaleSerializer(many=True)


class AwaitingPayoutSerializer(serializers.Serializer):
    def to_representation(self, event):
        gross, fee, net = compute_payout_amounts(event)
        available_at = payout_available_at(event)
        organizer = event.organizer
        return {
            "event_id": str(event.id),
            "event_title": event.title,
            "organizer_name": str(organizer).strip() or organizer.email,
            "venue_name": event.venue.name if event.venue else "",
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
