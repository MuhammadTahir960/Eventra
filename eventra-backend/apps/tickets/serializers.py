import re

from rest_framework import serializers

from .models import TICKET_CODE_ALPHABET, Ticket, format_ticket_code

_NOT_A_CODE = "That isn't a ticket code."


class TicketCodeSerializer(serializers.Serializer):
    code = serializers.CharField(
        max_length=32,
        error_messages=dict.fromkeys(
            ("blank", "null", "invalid", "max_length"), _NOT_A_CODE
        ),
    )

    def validate_code(self, value):
        raw = re.sub(r"[\s-]", "", value).upper()
        if len(raw) != 12 or any(char not in TICKET_CODE_ALPHABET for char in raw):
            raise serializers.ValidationError(_NOT_A_CODE)
        return format_ticket_code(raw)


class TicketSerializer(serializers.ModelSerializer):
    event_id = serializers.UUIDField(source="event_seat.event_id", read_only=True)
    event_title = serializers.CharField(source="event_seat.event.title", read_only=True)
    section = serializers.CharField(source="event_seat.seat.section", read_only=True)
    row_label = serializers.CharField(
        source="event_seat.seat.row_label", read_only=True
    )
    seat_number = serializers.IntegerField(
        source="event_seat.seat.seat_number", read_only=True
    )

    class Meta:
        model = Ticket
        fields = [
            "id",
            "booking",
            "event_id",
            "event_title",
            "section",
            "row_label",
            "seat_number",
            "ticket_code",
            "price",
            "attendee_name",
            "status",
            "created_at",
        ]
        read_only_fields = fields
