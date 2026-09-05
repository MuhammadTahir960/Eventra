from rest_framework import serializers

from .models import Ticket


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
            "attendee_name",
            "status",
            "created_at",
        ]
        read_only_fields = fields
