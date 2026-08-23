from django.conf import settings
from rest_framework import serializers

from apps.payments.models import Payment

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


class CheckoutResponseSerializer(serializers.ModelSerializer):
    client_secret = serializers.CharField()
    publishable_key = serializers.SerializerMethodField()

    class Meta:
        model = Payment
        fields = ["client_secret", "publishable_key", "amount", "currency", "status"]

    def get_publishable_key(self, obj):
        return settings.STRIPE_PUBLISHABLE_KEY
