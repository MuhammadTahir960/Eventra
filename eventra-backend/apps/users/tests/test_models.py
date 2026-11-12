import pytest
from django.db import IntegrityError, transaction

from apps.common.constants import Roles
from apps.users.models import User

from ..factories import UserFactory

pytestmark = pytest.mark.django_db


# ==================================================
# UserManager.create_user
# ==================================================


def test_create_user_hashes_password():
    user = User.objects.create_user(email="alice@example.com", password="s3cure-pass!")
    assert user.password != "s3cure-pass!"
    assert user.check_password("s3cure-pass!") is True


@pytest.mark.parametrize(
    "raw, stored",
    [
        ("Alice@EXAMPLE.COM", "alice@example.com"),
        ("  bob@example.com  ", "bob@example.com"),
    ],
)
def test_create_user_lowercases_and_trims_the_email(raw, stored):
    user = User.objects.create_user(email=raw, password="s3cure-pass!")
    assert user.email == stored


@pytest.mark.parametrize(
    "email, message",
    [("", "Users must have an email address"), ("not-an-email", "valid email address")],
)
def test_create_user_needs_a_valid_email(email, message):
    with pytest.raises(ValueError, match=message):
        User.objects.create_user(email=email, password="s3cure-pass!")


def test_create_user_defaults():
    user = User.objects.create_user(email="bob@example.com", password="s3cure-pass!")
    assert user.role == Roles.ATTENDEE
    assert user.is_active is False
    assert user.is_email_verified is False
    assert user.is_staff is False
    assert user.is_superuser is False


@pytest.mark.parametrize(
    "first, second",
    [
        ("dupe@example.com", "dupe@example.com"),
        ("Alice@Example.com", "alice@example.com"),
    ],
)
def test_email_uniqueness_enforced_at_db_level_in_any_case(first, second):
    User.objects.create_user(email=first, password="s3cure-pass!")
    with pytest.raises(IntegrityError):
        User.objects.create_user(email=second, password="another-pass!")


# ==================================================
# UserManager.create_superuser
# ==================================================


def test_create_superuser_grants_full_access():
    admin = User.objects.create_superuser(
        email="root@example.com", password="s3cure-pass!"
    )
    assert admin.is_staff is True
    assert admin.is_superuser is True
    assert admin.is_active is True
    assert admin.role == Roles.ADMIN


def test_create_superuser_rejects_explicit_is_staff_false():
    with pytest.raises(ValueError, match="is_staff=True"):
        User.objects.create_superuser(
            email="root2@example.com", password="s3cure-pass!", is_staff=False
        )


def test_create_superuser_rejects_explicit_is_superuser_false():
    with pytest.raises(ValueError, match="is_superuser=True"):
        User.objects.create_superuser(
            email="root3@example.com", password="s3cure-pass!", is_superuser=False
        )


# ==================================================
# Misc model behavior
# ==================================================


def test_str_returns_full_name():
    user = UserFactory(first_name="Ada", last_name="Lovelace")
    assert str(user) == "Ada Lovelace"


def test_username_field_is_email():
    assert User.USERNAME_FIELD == "email"
    assert User.REQUIRED_FIELDS == []


@pytest.mark.parametrize("role", [Roles.ATTENDEE, Roles.ORGANIZER])
def test_save_strips_django_admin_access_from_non_admin_roles(role):
    user = UserFactory(role=Roles.ADMIN, is_staff=True, is_superuser=True)

    user.role = role
    user.save(update_fields=["role"])

    user.refresh_from_db()
    assert user.is_staff is False
    assert user.is_superuser is False


def test_save_keeps_django_admin_access_for_admin_role():
    user = UserFactory(role=Roles.ADMIN, is_staff=True, is_superuser=True)
    user.save()
    user.refresh_from_db()
    assert user.is_staff is True
    assert user.is_superuser is True


@pytest.mark.parametrize(
    "first, second",
    [
        ("ana@gmail.com", "a.n.a+x@googlemail.com"),
        ("bo+old@example.com", "BO@example.com"),
    ],
)
def test_the_database_allows_one_account_per_mailbox(first, second):
    UserFactory(email=first)
    with pytest.raises(IntegrityError), transaction.atomic():
        UserFactory(email=second)


def test_different_mailboxes_are_still_allowed():
    UserFactory(email="a.na@example.com")
    UserFactory(email="ana@example.com")
