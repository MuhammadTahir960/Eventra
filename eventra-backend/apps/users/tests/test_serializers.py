import pytest
from rest_framework import serializers
from rest_framework_simplejwt.exceptions import AuthenticationFailed
from rest_framework_simplejwt.tokens import RefreshToken
from apps.common.constants import Roles
from apps.users.models import User
from apps.users.serializers import (
    ActiveUserTokenObtainPairSerializer,
    LogoutSerializer,
    RegisterSerializer,
    UserSerializer,
)
from ..factories import UserFactory

pytestmark = pytest.mark.django_db


# ==================================================
# RegisterSerializer
# ==================================================


def _register_payload(**overrides):
    payload = {
        "email": "newuser@example.com",
        "password": "a-genuinely-strong-pass-1",
        "first_name": "New",
        "last_name": "User",
    }
    payload.update(overrides)
    return payload


def test_register_serializer_valid_data_creates_user():
    serializer = RegisterSerializer(data=_register_payload())
    assert serializer.is_valid(), serializer.errors

    user = serializer.save()

    assert user.email == "newuser@example.com"
    assert user.password != "a-genuinely-strong-pass-1"
    assert user.check_password("a-genuinely-strong-pass-1") is True


def test_register_serializer_normalizes_email_casing():
    serializer = RegisterSerializer(
        data=_register_payload(email="  MixedCase@Example.COM  ")
    )
    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["email"] == "mixedcase@example.com"

    user = serializer.save()
    assert user.email == "mixedcase@example.com"


def test_register_serializer_password_write_only():
    serializer = RegisterSerializer(data=_register_payload())
    serializer.is_valid()
    serializer.save()
    assert "password" not in serializer.data


def test_register_serializer_rejects_short_password():
    serializer = RegisterSerializer(data=_register_payload(password="short1"))
    assert serializer.is_valid() is False
    assert "too short" in str(serializer.errors).lower()


def test_register_serializer_rejects_common_password():
    serializer = RegisterSerializer(data=_register_payload(password="password123"))
    assert serializer.is_valid() is False
    assert "too common" in str(serializer.errors).lower()


def test_register_serializer_rejects_password_similar_to_email():
    serializer = RegisterSerializer(
        data=_register_payload(
            email="janedoe@example.com", password="janedoe@example.com"
        )
    )
    assert serializer.is_valid() is False
    assert "too similar" in str(serializer.errors).lower()


def test_register_serializer_duplicate_email_rejected():
    UserFactory(email="taken@example.com")
    serializer = RegisterSerializer(data=_register_payload(email="taken@example.com"))
    assert serializer.is_valid() is False
    assert "email" in serializer.errors


def test_register_serializer_duplicate_email_rejected_case_insensitive():
    UserFactory(email="taken@example.com")
    serializer = RegisterSerializer(data=_register_payload(email="Taken@Example.com"))
    assert serializer.is_valid() is False
    assert "email" in serializer.errors


def test_register_serializer_rejects_invalid_email_format():
    serializer = RegisterSerializer(data=_register_payload(email="not-an-email"))
    assert serializer.is_valid() is False
    assert "email" in serializer.errors


def test_register_serializer_rejects_first_name_over_max_length():
    serializer = RegisterSerializer(data=_register_payload(first_name="A" * 31))
    assert serializer.is_valid() is False
    assert "first_name" in serializer.errors


def test_register_serializer_rejects_last_name_over_max_length():
    serializer = RegisterSerializer(data=_register_payload(last_name="B" * 31))
    assert serializer.is_valid() is False
    assert "last_name" in serializer.errors


def test_register_serializer_ignores_privileged_field_injection():
    payload = _register_payload(
        email="attacker@example.com",
        role=Roles.ADMIN,
        is_staff=True,
        is_superuser=True,
        is_active=True,
    )
    serializer = RegisterSerializer(data=payload)
    assert serializer.is_valid(), serializer.errors

    assert "role" not in serializer.validated_data
    assert "is_staff" not in serializer.validated_data
    assert "is_superuser" not in serializer.validated_data
    assert "is_active" not in serializer.validated_data

    user = serializer.save()
    assert user.role == Roles.ATTENDEE
    assert user.is_staff is False
    assert user.is_superuser is False
    assert user.is_active is False


# ==================================================
# ActiveUserTokenObtainPairSerializer
# ==================================================


def test_login_serializer_valid_active_user_returns_tokens():
    UserFactory(email="active@example.com", is_active=True)
    serializer = ActiveUserTokenObtainPairSerializer(
        data={"email": "active@example.com", "password": "testpass123"}
    )
    assert serializer.is_valid(), serializer.errors
    assert "access" in serializer.validated_data
    assert "refresh" in serializer.validated_data


def test_login_serializer_rejects_inactive_user():
    UserFactory(email="unverified@example.com", is_active=False)
    serializer = ActiveUserTokenObtainPairSerializer(
        data={"email": "unverified@example.com", "password": "testpass123"}
    )
    with pytest.raises(AuthenticationFailed, match="not active"):
        serializer.is_valid(raise_exception=True)


def test_login_serializer_rejects_wrong_password():
    UserFactory(email="active@example.com", is_active=True)
    serializer = ActiveUserTokenObtainPairSerializer(
        data={"email": "active@example.com", "password": "totally-wrong"}
    )
    with pytest.raises(AuthenticationFailed):
        serializer.is_valid(raise_exception=True)


def test_login_serializer_rejects_nonexistent_email():
    serializer = ActiveUserTokenObtainPairSerializer(
        data={"email": "nobody@example.com", "password": "whatever123"}
    )
    with pytest.raises(AuthenticationFailed):
        serializer.is_valid(raise_exception=True)


def test_login_serializer_missing_email_rejected():
    serializer = ActiveUserTokenObtainPairSerializer(data={"password": "testpass123"})
    assert serializer.is_valid() is False
    assert "email" in serializer.errors


def test_login_serializer_missing_password_rejected():
    serializer = ActiveUserTokenObtainPairSerializer(
        data={"email": "active@example.com"}
    )
    assert serializer.is_valid() is False
    assert "password" in serializer.errors


def test_login_serializer_email_lookup_is_case_insensitive():
    UserFactory(email="Active@Example.com", is_active=True)
    serializer = ActiveUserTokenObtainPairSerializer(
        data={"email": "active@example.com", "password": "testpass123"}
    )
    assert serializer.is_valid(), serializer.errors


def test_login_serializer_error_message_does_not_leak_account_existence():
    UserFactory(email="active@example.com", is_active=True)

    wrong_password = ActiveUserTokenObtainPairSerializer(
        data={"email": "active@example.com", "password": "totally-wrong"}
    )
    no_such_user = ActiveUserTokenObtainPairSerializer(
        data={"email": "nobody@example.com", "password": "whatever123"}
    )

    msg_1 = _get_auth_failed_message(wrong_password)
    msg_2 = _get_auth_failed_message(no_such_user)
    assert msg_1 == msg_2


def test_login_serializer_nonexistent_email_still_runs_a_password_check():
    from unittest.mock import patch

    with patch.object(User, "set_password") as mocked_set_password:
        serializer = ActiveUserTokenObtainPairSerializer(
            data={"email": "nobody@example.com", "password": "whatever123"}
        )
        with pytest.raises(AuthenticationFailed):
            serializer.is_valid(raise_exception=True)

    mocked_set_password.assert_called_once_with("whatever123")


def _get_auth_failed_message(serializer):
    try:
        serializer.is_valid(raise_exception=True)
    except AuthenticationFailed as exc:
        return str(exc.detail)
    raise AssertionError("expected AuthenticationFailed to be raised")


# ==================================================
# LogoutSerializer
# ==================================================


def test_logout_serializer_blacklists_valid_refresh_token():
    user = UserFactory()
    refresh = RefreshToken.for_user(user)

    serializer = LogoutSerializer(data={"refresh": str(refresh)})
    assert serializer.is_valid(), serializer.errors
    serializer.save()

    with pytest.raises(Exception):
        RefreshToken(str(refresh)).blacklist()


def test_logout_serializer_rejects_invalid_token():
    serializer = LogoutSerializer(data={"refresh": "not-a-real-token"})
    serializer.is_valid()
    with pytest.raises(Exception):
        serializer.save()


def test_logout_serializer_invalid_token_error_scoped_to_refresh_field():
    serializer = LogoutSerializer(data={"refresh": "not-a-real-token"})
    serializer.is_valid()
    with pytest.raises(serializers.ValidationError) as exc_info:
        serializer.save()
    assert "refresh" in exc_info.value.detail


def test_logout_serializer_rejects_missing_refresh_field():
    serializer = LogoutSerializer(data={})
    assert serializer.is_valid() is False
    assert "refresh" in serializer.errors


def test_logout_serializer_rejects_already_blacklisted_token():
    user = UserFactory()
    refresh = RefreshToken.for_user(user)

    first = LogoutSerializer(data={"refresh": str(refresh)})
    first.is_valid()
    first.save()

    second = LogoutSerializer(data={"refresh": str(refresh)})
    second.is_valid()
    with pytest.raises(Exception):
        second.save()


# ==================================================
# UserSerializer
# ==================================================


def test_user_serializer_exposes_expected_fields():
    user = UserFactory(first_name="Ada", last_name="Lovelace")
    data = UserSerializer(user).data
    assert data["email"] == user.email
    assert data["first_name"] == "Ada"
    assert data["last_name"] == "Lovelace"
    assert data["role"] == Roles.ATTENDEE
    assert "password" not in data


def test_user_serializer_email_and_role_are_read_only():
    user = UserFactory(email="original@example.com", role=Roles.ATTENDEE)
    serializer = UserSerializer(
        user,
        data={
            "email": "hacked@example.com",
            "role": Roles.ADMIN,
            "first_name": "Changed",
        },
        partial=True,
    )
    assert serializer.is_valid(), serializer.errors
    updated = serializer.save()

    assert updated.email == "original@example.com"
    assert updated.role == Roles.ATTENDEE
    assert updated.first_name == "Changed"
