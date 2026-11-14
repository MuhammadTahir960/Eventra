from django.conf import settings
from rest_framework import serializers

from apps.common.serializers import RejectUnknownFieldsMixin


class CheckoutResponseSerializer(serializers.Serializer):
    client_secret = serializers.CharField(read_only=True)
    publishable_key = serializers.SerializerMethodField()
    status = serializers.CharField(read_only=True)

    def get_publishable_key(self, obj):
        return settings.STRIPE_PUBLISHABLE_KEY


class PartialRefundSerializer(RejectUnknownFieldsMixin, serializers.Serializer):
    percent = serializers.IntegerField(min_value=1, max_value=99)
