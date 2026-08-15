from django.db.models import Q
from django.utils.text import slugify

from .models import Category


class DuplicateCategoryError(Exception):
    """
    Raised when an *active* category with the same name/slug already exists.
    """


class InactiveDuplicateCategoryError(DuplicateCategoryError):
    """
    Raised when a *soft-deleted* category with the same name/slug already exists.
    """


def find_conflicting_category(name: str, *, exclude_pk=None) -> Category | None:
    slug = slugify(name, allow_unicode=True)
    qs = Category.all_objects.filter(Q(name__iexact=name) | Q(slug__iexact=slug))
    if exclude_pk is not None:
        qs = qs.exclude(pk=exclude_pk)
    return qs.first()


def ensure_unique_category_name(name: str, *, exclude_pk=None) -> None:
    conflict = find_conflicting_category(name, exclude_pk=exclude_pk)
    if conflict is None:
        return

    if not conflict.is_active:
        raise InactiveDuplicateCategoryError(
            "A category with this name or slug already exists (inactive). "
            "Please restore the existing category."
        )
    raise DuplicateCategoryError("A category with this name or slug already exists.")


def ensure_can_restore_category(instance: Category) -> None:
    conflict = Category.objects.filter(
        Q(name__iexact=instance.name) | Q(slug__iexact=instance.slug)
    ).first()
    if conflict is not None:
        raise DuplicateCategoryError(
            "Cannot restore: an active category with this name or slug already exists."
        )
