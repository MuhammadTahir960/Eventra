import pytest
from django.db import IntegrityError
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


def test_create_user_normalizes_email_to_fully_lowercase():
    user = User.objects.create_user(email="Alice@EXAMPLE.COM", password="s3cure-pass!")
    assert user.email == "alice@example.com"


def test_create_user_strips_surrounding_whitespace():
    user = User.objects.create_user(
        email="  bob@example.com  ", password="s3cure-pass!"
    )
    assert user.email == "bob@example.com"


def test_create_user_without_email_raises():
    with pytest.raises(ValueError, match="Users must have an email address"):
        User.objects.create_user(email="", password="s3cure-pass!")


def test_create_user_rejects_malformed_email():
    with pytest.raises(ValueError, match="valid email address"):
        User.objects.create_user(email="not-an-email", password="s3cure-pass!")


def test_create_user_defaults():
    user = User.objects.create_user(email="bob@example.com", password="s3cure-pass!")
    assert user.role == Roles.ATTENDEE
    assert user.is_active is False
    assert user.is_email_verified is False
    assert user.is_staff is False
    assert user.is_superuser is False


def test_email_uniqueness_enforced_at_db_level():
    User.objects.create_user(email="dupe@example.com", password="s3cure-pass!")
    with pytest.raises(IntegrityError):
        User.objects.create_user(email="dupe@example.com", password="another-pass!")


def test_email_uniqueness_enforced_across_local_part_case_variants():
    User.objects.create_user(email="Alice@Example.com", password="s3cure-pass!")
    with pytest.raises(IntegrityError):
        User.objects.create_user(email="alice@example.com", password="another-pass!")


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
