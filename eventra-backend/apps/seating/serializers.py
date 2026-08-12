from rest_framework import serializers
from .models import EventSeat
from .services import MAX_SEATS_PER_HOLD


class EventSeatSerializer(serializers.ModelSerializer):
    section = serializers.CharField(source="seat.section", read_only=True)
    row_label = serializers.CharField(source="seat.row_label", read_only=True)
    seat_number = serializers.IntegerField(source="seat.seat_number", read_only=True)
    tier_name = serializers.CharField(source="ticket_tier.name", read_only=True)
    price = serializers.SerializerMethodField()

    class Meta:
        model = EventSeat
        fields = [
            "id",
            "section",
            "row_label",
            "seat_number",
            "ticket_tier",
            "tier_name",
            "price",
            "status",
        ]
        read_only_fields = fields

    def get_price(self, obj: EventSeat):
        return (
            obj.price_override
            if obj.price_override is not None
            else obj.ticket_tier.price
        )


class SeatHoldRequestSerializer(serializers.Serializer):
    seat_ids = serializers.ListField(
        child=serializers.UUIDField(),
        allow_empty=False,
        max_length=MAX_SEATS_PER_HOLD,
    )
