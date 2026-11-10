import pytest

from ..factories import CategoryFactory
from ..serializers import CategorySerializer

pytestmark = pytest.mark.django_db


def _payload(**overrides):
    payload = {"name": "New Category", "icon": "music", "sort_order": 0}
    payload.update(overrides)
    return payload


# ==================================================
# Happy path
# ==================================================


def test_valid_payload_creates_category():
    serializer = CategorySerializer(data=_payload())
    assert serializer.is_valid(), serializer.errors
    category = serializer.save()
    assert category.name == "New Category"
    assert category.slug == "new-category"


def test_id_and_slug_are_read_only():
    serializer = CategorySerializer(data=_payload())
    serializer.is_valid()
    category = serializer.save()
    data = CategorySerializer(category).data
    assert data["slug"] == "new-category"
    assert "id" in data


# ==================================================
# Duplicate-name validation
# ==================================================


@pytest.mark.parametrize("name", ["Music", "MUSIC"])
def test_duplicate_active_name_rejected(name):
    CategoryFactory(name="Music")
    serializer = CategorySerializer(data=_payload(name=name))
    assert serializer.is_valid() is False
    assert "name" in serializer.errors


def test_duplicate_against_soft_deleted_category_gives_restore_hint():
    CategoryFactory(name="Music", is_active=False)
    serializer = CategorySerializer(data=_payload(name="Music"))
    assert serializer.is_valid() is False
    assert "restore" in str(serializer.errors["name"]).lower()


def test_unique_name_is_accepted():
    CategoryFactory(name="Music")
    serializer = CategorySerializer(data=_payload(name="Sports"))
    assert serializer.is_valid(), serializer.errors


def test_race_condition_integrity_error_becomes_validation_error():
    from rest_framework import serializers as drf_serializers

    CategoryFactory(name="Music")
    serializer = CategorySerializer()
    with pytest.raises(drf_serializers.ValidationError):
        serializer.create(_payload(name="Music"))


def test_update_race_condition_integrity_error_becomes_validation_error():
    from rest_framework import serializers as drf_serializers

    CategoryFactory(name="Music")
    other = CategoryFactory(name="Sports")
    serializer = CategorySerializer()
    with pytest.raises(drf_serializers.ValidationError):
        serializer.update(other, {"name": "Music"})


# ==================================================
# Update behavior
# ==================================================


def test_update_excludes_self_from_duplicate_check():
    category = CategoryFactory(name="Music")
    serializer = CategorySerializer(category, data={"sort_order": 5}, partial=True)
    assert serializer.is_valid(), serializer.errors


def test_partial_update_without_name_still_validates_against_existing_name():
    category = CategoryFactory(name="Music")
    serializer = CategorySerializer(category, data={"icon": "tools"}, partial=True)
    assert serializer.is_valid(), serializer.errors


def test_update_into_a_conflicting_name_rejected():
    CategoryFactory(name="Sports")
    category = CategoryFactory(name="Music")
    serializer = CategorySerializer(category, data={"name": "Sports"}, partial=True)
    assert serializer.is_valid() is False
    assert "name" in serializer.errors


# ==================================================
# Field validation
# ==================================================


def test_missing_name_rejected():
    serializer = CategorySerializer(data={"icon": "music"})
    assert serializer.is_valid() is False
    assert "name" in serializer.errors


def test_blank_name_rejected():
    serializer = CategorySerializer(data=_payload(name=""))
    assert serializer.is_valid() is False
    assert "name" in serializer.errors


def test_negative_sort_order_rejected():
    serializer = CategorySerializer(data=_payload(sort_order=-1))
    assert serializer.is_valid() is False
    assert "sort_order" in serializer.errors


def test_name_over_max_length_rejected():
    serializer = CategorySerializer(data=_payload(name="A" * 101))
    assert serializer.is_valid() is False
    assert "name" in serializer.errors


@pytest.mark.parametrize("icon", ["star", "<svg>", "", "x" * 30])
def test_icon_must_be_one_of_the_known_keys(icon):
    serializer = CategorySerializer(data=_payload(name="Jazz Nights", icon=icon))
    assert not serializer.is_valid()
    assert "icon" in serializer.errors
