from rest_framework import serializers

from apps.common.serializers import RejectUnknownFieldsMixin

from .models import Booking


class HoldIdSerializer(RejectUnknownFieldsMixin, serializers.Serializer):

    hold_id = serializers.UUIDField()


class BookingSerializer(serializers.ModelSerializer):
    total_amount = serializers.DecimalField(
        max_digits=18, decimal_places=2, read_only=True
    )
    currency = serializers.CharField(
        source="event.currency", read_only=True, allow_null=True
    )

    class Meta:
        model = Booking
        fields = [
            "id",
            "status",
            "total_amount",
            "currency",
            "source_hold_group_id",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields
