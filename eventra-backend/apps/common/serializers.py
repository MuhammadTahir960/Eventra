from django.db import IntegrityError, transaction
from rest_framework import serializers


class IntegrityErrorHandlingMixin:
    integrity_error_field = "non_field_errors"
    integrity_error_message = "This conflicts with an existing record."

    def create(self, validated_data):
        try:
            with transaction.atomic():
                return super().create(validated_data)
        except IntegrityError as exc:
            raise serializers.ValidationError(
                {self.integrity_error_field: self.integrity_error_message}
            ) from exc

    def update(self, instance, validated_data):
        try:
            with transaction.atomic():
                return super().update(instance, validated_data)
        except IntegrityError as exc:
            raise serializers.ValidationError(
                {self.integrity_error_field: self.integrity_error_message}
            ) from exc
