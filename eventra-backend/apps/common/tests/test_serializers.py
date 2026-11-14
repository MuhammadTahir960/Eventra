import importlib
import inspect
import pkgutil

import pytest
from django.db import IntegrityError
from rest_framework import serializers

import apps
from apps.common.serializers import RejectUnknownFieldsMixin

from ..serializers import IntegrityErrorHandlingMixin


class _Pair(RejectUnknownFieldsMixin, serializers.Serializer):
    name = serializers.CharField()
    slug = serializers.CharField(read_only=True)


def test_known_fields_pass():
    serializer = _Pair(data={"name": "A"})
    assert serializer.is_valid(), serializer.errors


@pytest.mark.parametrize("extra", [{"role": "admin"}, {"slug": "chosen"}])
def test_unknown_and_read_only_fields_are_refused(extra):
    serializer = _Pair(data={"name": "A", **extra})
    assert not serializer.is_valid()
    assert set(serializer.errors) == set(extra)


def test_a_flood_of_unknown_fields_gets_a_short_answer():
    serializer = _Pair(data={"name": "A", **{f"junk{i:04}": 1 for i in range(5000)}})
    assert not serializer.is_valid()
    assert len(serializer.errors) == 10


def _input_serializers():
    for module_info in pkgutil.walk_packages(apps.__path__, "apps."):
        if not module_info.name.endswith(".serializers"):
            continue
        module = importlib.import_module(module_info.name)
        for _, cls in inspect.getmembers(module, inspect.isclass):
            if (
                issubclass(cls, serializers.BaseSerializer)
                and cls.__module__ == module.__name__
                and any(not field.read_only for field in cls().fields.values())
            ):
                yield cls


def test_every_serializer_that_takes_input_refuses_unknown_fields():
    missing = [
        f"{cls.__module__}.{cls.__name__}"
        for cls in _input_serializers()
        if not issubclass(cls, RejectUnknownFieldsMixin)
    ]
    assert missing == []


# ==================================================
# IntegrityErrorHandlingMixin — default field/message
# ==================================================


class _RaisesIntegrityError:
    def create(self, validated_data):
        raise IntegrityError("duplicate key value violates unique constraint")

    def update(self, instance, validated_data):
        raise IntegrityError("duplicate key value violates unique constraint")


class _DefaultIntegrityErrorSerializer(
    IntegrityErrorHandlingMixin, _RaisesIntegrityError
):
    """
    Deliberately does NOT override integrity_error_field/message, so the
    mixin's create()/update() are exercised with the mixin's own defaults.
    """


@pytest.mark.django_db
def test_integrity_error_mixin_default_create_message():
    serializer = _DefaultIntegrityErrorSerializer()
    with pytest.raises(serializers.ValidationError) as exc_info:
        serializer.create({})
    assert exc_info.value.detail["non_field_errors"] == (
        "This conflicts with an existing record."
    )


@pytest.mark.django_db
def test_integrity_error_mixin_default_update_message():
    serializer = _DefaultIntegrityErrorSerializer()
    with pytest.raises(serializers.ValidationError) as exc_info:
        serializer.update(instance=None, validated_data={})
    assert exc_info.value.detail["non_field_errors"] == (
        "This conflicts with an existing record."
    )
