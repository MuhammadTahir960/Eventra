from django.db import IntegrityError, transaction
from rest_framework import serializers

from .validators import (
    validate_multiline_text,
    validate_person_name,
    validate_single_line_text,
)


class AllowedTextMixin:
    def get_fields(self):
        fields = super().get_fields()
        for field in fields.values():
            if (
                type(field) is serializers.CharField
                and not field.read_only
                and not field.write_only
            ):
                multiline = field.style.get("base_template") == "textarea.html"
                field.validators.append(
                    validate_multiline_text if multiline else validate_single_line_text
                )
        return fields


class PersonNameMixin:
    def validate_first_name(self, value):
        validate_person_name(value)
        return value

    def validate_last_name(self, value):
        validate_person_name(value)
        return value


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
