import factory
from factory.django import DjangoModelFactory

from apps.categories.models import Category


class CategoryFactory(DjangoModelFactory):
    class Meta:
        model = Category

    name = factory.Sequence(lambda n: f"Category {n}")
    icon = "star"
    sort_order = 0
    is_active = True
