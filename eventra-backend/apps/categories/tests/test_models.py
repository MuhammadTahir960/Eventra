import pytest
from django.db import IntegrityError
from ..models import Category
from ..factories import CategoryFactory

pytestmark = pytest.mark.django_db


# ==================================================
# Uniqueness constraints (active rows only)
# ==================================================


def test_duplicate_active_name_rejected_at_db_level():
    CategoryFactory(name="Music")
    with pytest.raises(IntegrityError):
        CategoryFactory(name="Music")


def test_duplicate_active_slug_rejected_at_db_level():
    CategoryFactory(name="Music")
    with pytest.raises(IntegrityError):
        Category.objects.create(name="Different Name", slug="music")


def test_same_name_allowed_when_original_is_soft_deleted():
    CategoryFactory(name="Music", is_active=False)
    CategoryFactory(name="Music")


# ==================================================
# Slug auto-generation
# ==================================================


def test_slug_is_auto_generated_from_name_when_blank():
    category = CategoryFactory(name="Live Music Events", slug="")
    assert category.slug == "live-music-events"


def test_explicit_slug_is_preserved():
    category = CategoryFactory(name="Live Music Events", slug="custom-slug")
    assert category.slug == "custom-slug"


def test_slug_supports_unicode_names():
    category = CategoryFactory(name="Café Culture", slug="")
    assert category.slug


# ==================================================
# Soft delete manager behavior
# ==================================================


def test_default_manager_excludes_inactive_categories():
    CategoryFactory(is_active=True)
    CategoryFactory(is_active=False)
    assert Category.objects.count() == 1


def test_all_objects_manager_includes_inactive_categories():
    CategoryFactory(is_active=True)
    CategoryFactory(is_active=False)
    assert Category.all_objects.count() == 2


# ==================================================
# Misc
# ==================================================


def test_str_returns_name():
    category = CategoryFactory(name="Sports Events")
    assert str(category) == "Sports Events"


def test_default_ordering_is_by_sort_order_then_name():
    CategoryFactory(name="Zebra", sort_order=1)
    CategoryFactory(name="Alpha", sort_order=1)
    CategoryFactory(name="Beta", sort_order=0)
    names = list(Category.objects.values_list("name", flat=True))
    assert names == ["Beta", "Alpha", "Zebra"]
