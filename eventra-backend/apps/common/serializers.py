from django.db import IntegrityError, transaction
from rest_framework import serializers

from .validators import (
    validate_multiline_text,
    validate_single_line_text,
)


class RejectUnknownFieldsMixin:
    def to_internal_value(self, data):
        if hasattr(data, "keys"):
            accepted = {
                name for name, field in self.fields.items() if not field.read_only
            }
            unknown = sorted(set(data.keys()) - accepted)
            if unknown:
                raise serializers.ValidationError(
                    {name: ["This field isn't accepted here."] for name in unknown[:10]}
                )
        return super().to_internal_value(data)


class StrictCharField(serializers.CharField):
    def to_internal_value(self, data):
        if not isinstance(data, str):
            self.fail("invalid")
        return super().to_internal_value(data)


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
