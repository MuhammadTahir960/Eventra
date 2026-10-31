import importlib

import pytest
from django.apps import apps
from django.db import IntegrityError

from apps.events.factories import EventFactory

from ..factories import CategoryFactory
from ..models import Category

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


def test_slug_regenerates_on_rename():
    category = CategoryFactory(name="Live Music Events", slug="")
    assert category.slug == "live-music-events"

    category.name = "Live Comedy Events"
    category.save()

    assert category.slug == "live-comedy-events"


def test_slug_unchanged_when_name_unchanged():
    category = CategoryFactory(name="Live Music Events", slug="")
    original_slug = category.slug

    category.icon = "music-note"
    category.save()

    assert category.slug == original_slug


def test_explicit_slug_still_regenerates_on_rename():
    category = CategoryFactory(name="Live Music Events", slug="custom-slug")

    category.name = "Live Comedy Events"
    category.save()

    assert category.slug == "live-comedy-events"


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


migration = importlib.import_module("apps.categories.migrations.0003_final_categories")


def run():
    migration.add_final_categories(apps, None)


def test_creates_the_final_list_once_even_when_run_again():
    run()
    run()
    names = list(Category.objects.values_list("name", flat=True))
    assert names == migration.FINAL_CATEGORIES
    assert list(
        Category.objects.filter(admin_only=True).values_list("name", flat=True)
    ) == ["Sports"]


def test_old_names_are_renamed_and_keep_their_events():
    Category.objects.all().delete()
    music = Category.objects.create(name="Music")
    event = EventFactory(category=music)
    run()
    music.refresh_from_db()
    assert music.name == "Concerts & Live Music"
    assert music.slug == "concerts-live-music"
    event.refresh_from_db()
    assert event.category_id == music.id
    assert Category.objects.filter(name__iexact="concerts & live music").count() == 1
