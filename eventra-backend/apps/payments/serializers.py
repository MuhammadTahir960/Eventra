from django.conf import settings
from rest_framework import serializers

from .models import Payment


class CheckoutResponseSerializer(serializers.ModelSerializer):
    client_secret = serializers.CharField()
    publishable_key = serializers.SerializerMethodField()

    class Meta:
        model = Payment
        fields = ["client_secret", "publishable_key", "amount", "currency", "status"]

    def get_publishable_key(self, obj):
        return settings.STRIPE_PUBLISHABLE_KEY
