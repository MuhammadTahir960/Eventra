import pytest

from ..models import Category


@pytest.fixture(autouse=True)
def _no_default_categories(db):
    Category.all_objects.all().delete()
