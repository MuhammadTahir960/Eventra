import factory
from factory.django import DjangoModelFactory

from apps.common.constants import Roles
from apps.payouts import account_numbers
from apps.payouts.models import PayoutAccount
from apps.users.models import User


def new_account_number() -> bytes:
    return account_numbers.encrypt(account_numbers.issue()["number"])


def add_payout_account(**fields) -> PayoutAccount:
    return PayoutAccount.objects.create(
        method=PayoutAccount.Method.BANK,
        provider="Test Bank",
        account_number=new_account_number(),
        **fields,
    )


class UserFactory(DjangoModelFactory):
    class Meta:
        model = User
        skip_postgeneration_save = True

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

    @factory.post_generation
    def payout_account(user, create, extracted, **kwargs):
        if create and user.role == Roles.ORGANIZER and extracted is not False:
            add_payout_account(organizer=user, holder_name=user.full_name)
