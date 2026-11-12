from django.conf import settings
from rest_framework import serializers


class CheckoutResponseSerializer(serializers.Serializer):
    client_secret = serializers.CharField()
    publishable_key = serializers.SerializerMethodField()
    status = serializers.CharField()

    def get_publishable_key(self, obj):
        return settings.STRIPE_PUBLISHABLE_KEY


class PartialRefundSerializer(serializers.Serializer):
    percent = serializers.IntegerField(min_value=1, max_value=99)
