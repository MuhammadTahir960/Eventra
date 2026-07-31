import pytest
from ..factories import CategoryFactory
from ..services import (
    DuplicateCategoryError,
    InactiveDuplicateCategoryError,
    ensure_can_restore_category,
    ensure_unique_category_name,
    find_conflicting_category,
)

pytestmark = pytest.mark.django_db


# ==================================================
# find_conflicting_category
# ==================================================


def test_returns_none_when_no_conflict_exists():
    assert find_conflicting_category("Music") is None


def test_finds_conflict_by_exact_name():
    existing = CategoryFactory(name="Music")
    assert find_conflicting_category("Music") == existing


def test_finds_conflict_case_insensitively():
    existing = CategoryFactory(name="Music")
    assert find_conflicting_category("MUSIC") == existing


def test_finds_conflict_via_derived_slug_even_with_different_name():
    existing = CategoryFactory(name="Something Else", slug="rock-roll")
    assert find_conflicting_category("Rock & Roll") == existing


def test_finds_conflict_among_soft_deleted_rows():
    existing = CategoryFactory(name="Music", is_active=False)
    assert find_conflicting_category("Music") == existing


def test_exclude_pk_omits_the_given_row():
    existing = CategoryFactory(name="Music")
    assert find_conflicting_category("Music", exclude_pk=existing.pk) is None


# ==================================================
# ensure_unique_category_name
# ==================================================


def test_no_exception_when_name_is_free():
    ensure_unique_category_name("Brand New Category")


def test_raises_duplicate_error_for_active_conflict():
    CategoryFactory(name="Music")
    with pytest.raises(DuplicateCategoryError):
        ensure_unique_category_name("Music")


def test_raises_inactive_duplicate_error_for_soft_deleted_conflict():
    CategoryFactory(name="Music", is_active=False)
    with pytest.raises(InactiveDuplicateCategoryError):
        ensure_unique_category_name("Music")


def test_inactive_duplicate_error_is_a_duplicate_category_error():
    CategoryFactory(name="Music", is_active=False)
    with pytest.raises(DuplicateCategoryError):
        ensure_unique_category_name("Music")


def test_exclude_pk_allows_updating_a_row_with_its_own_name():
    existing = CategoryFactory(name="Music")
    ensure_unique_category_name("Music", exclude_pk=existing.pk)


# ==================================================
# ensure_can_restore_category
# ==================================================


def test_restore_allowed_when_no_active_conflict():
    deleted = CategoryFactory(name="Music", is_active=False)
    ensure_can_restore_category(deleted)


def test_restore_blocked_when_active_conflict_exists():
    CategoryFactory(name="Music", is_active=True)
    deleted = CategoryFactory(name="Music", is_active=False)
    with pytest.raises(DuplicateCategoryError):
        ensure_can_restore_category(deleted)


def test_restore_allowed_when_conflict_is_also_soft_deleted():
    CategoryFactory(name="Music", is_active=False)
    deleted = CategoryFactory(name="Music", is_active=False)
    ensure_can_restore_category(deleted)
