import factory
from factory.django import DjangoModelFactory

from apps.common.constants import Roles
from apps.users.models import User


class UserFactory(DjangoModelFactory):
    class Meta:
        model = User

    email = factory.Sequence(lambda n: f"user{n}@example.com")
    first_name = factory.Faker("first_name")
    last_name = factory.Faker("last_name")
    role = Roles.ATTENDEE
    gender = User.Gender.OTHER
    is_active = True
    password = "testpass123"  # noqa: S105 (test users only; create_user() hashes it)

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        manager = cls._get_manager(model_class)
        return manager.create_user(*args, **kwargs)
