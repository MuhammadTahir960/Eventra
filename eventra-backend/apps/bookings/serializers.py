from rest_framework import serializers

from .models import Booking


class HoldIdSerializer(serializers.Serializer):

    hold_id = serializers.UUIDField()


class BookingSerializer(serializers.ModelSerializer):

    class Meta:
        model = Booking
        fields = [
            "id",
            "status",
            "total_amount",
            "source_hold_group_id",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields
