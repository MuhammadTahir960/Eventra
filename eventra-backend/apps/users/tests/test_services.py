import uuid
from unittest.mock import patch

import pytest
from django.core import mail

from apps.users.tokens import verify_password_reset_token, verify_token

from ..factories import UserFactory
from ..models import User
from ..serializers import RegisterSerializer
from ..services import (
    register_user,
    request_password_reset,
    reset_password,
    send_password_reset_email,
    send_verification_email,
    verify_user_email,
)
from ..tokens import generate_password_reset_token, generate_verification_token


@pytest.fixture(autouse=True)
def use_locmem_email_backend(settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"


# ==================================================
# send_verification_email
# ==================================================


@pytest.mark.django_db
def test_send_verification_email_contains_working_token():
    user = UserFactory(is_active=False)
    send_verification_email(user)

    assert len(mail.outbox) == 1
    sent = mail.outbox[0]
    assert sent.to == [user.email]
    assert "verify-email/?token=" in sent.body

    token = sent.body.split("token=")[1].strip()

    assert verify_token(token) == str(user.id)


@pytest.mark.django_db
def test_verification_email_link_points_at_the_real_backend_endpoint(settings):
    settings.BACKEND_BASE_URL = "http://api.example.test"
    settings.FRONTEND_URL = "http://app.example.test"

    user = UserFactory(is_active=False)
    send_verification_email(user)

    sent = mail.outbox[0]
    assert "http://api.example.test/auth/verify-email/?token=" in sent.body
    assert "app.example.test" not in sent.body


# ==================================================
# register_user
# ==================================================


@pytest.mark.django_db(transaction=True)
def test_register_user_creates_user_and_sends_email_after_commit():
    serializer = RegisterSerializer(
        data={
            "email": "newuser@example.com",
            "password": "a-genuinely-strong-pass-1",
            "first_name": "New",
            "last_name": "User",
        }
    )
    assert serializer.is_valid(), serializer.errors

    user = register_user(serializer)

    assert user.pk is not None
    assert user.is_active is False
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == [user.email]


@pytest.mark.django_db(transaction=True)
def test_register_user_survives_email_send_failure(caplog):

    serializer = RegisterSerializer(
        data={
            "email": "resilient@example.com",
            "password": "a-genuinely-strong-pass-1",
            "first_name": "New",
            "last_name": "User",
        }
    )
    assert serializer.is_valid(), serializer.errors

    with patch(
        "apps.users.services.send_verification_email",
        side_effect=RuntimeError("SMTP is down"),
    ), caplog.at_level("ERROR"):
        user = register_user(serializer)

    assert user.pk is not None
    assert User.objects.filter(email="resilient@example.com").exists()
    assert len(mail.outbox) == 0
    assert "Failed to send verification email" in caplog.text


# ==================================================
# verify_user_email
# ==================================================


@pytest.mark.django_db
def test_verify_user_email_activates_unverified_user():
    user = UserFactory(is_active=False, is_email_verified=False)
    token = generate_verification_token(user.id)

    result = verify_user_email(token)

    assert result is not None
    verified_user, was_newly_verified = result
    assert was_newly_verified is True
    verified_user.refresh_from_db()
    assert verified_user.is_active is True
    assert verified_user.is_email_verified is True


@pytest.mark.django_db
def test_verify_user_email_replay_is_idempotent_not_an_error():
    user = UserFactory(is_active=False, is_email_verified=False)
    token = generate_verification_token(user.id)

    verify_user_email(token)
    result = verify_user_email(token)

    assert result is not None
    _, was_newly_verified = result
    assert was_newly_verified is False


@pytest.mark.django_db
def test_verify_user_email_invalid_token_returns_none():
    assert verify_user_email("garbage-token") is None


@pytest.mark.django_db
def test_verify_user_email_token_for_deleted_user_returns_none():
    nonexistent_user_id = uuid.uuid4()
    token = generate_verification_token(nonexistent_user_id)
    assert verify_user_email(token) is None


@pytest.mark.django_db
def test_verify_user_email_bumps_last_updated():
    user = UserFactory(is_active=False, is_email_verified=False)
    original_last_updated = user.last_updated
    token = generate_verification_token(user.id)

    verify_user_email(token)

    user.refresh_from_db()
    assert user.last_updated > original_last_updated


# ==================================================
# send_password_reset_email
# ==================================================


@pytest.mark.django_db
def test_send_password_reset_email_contains_working_token():
    user = UserFactory()
    send_password_reset_email(user)

    assert len(mail.outbox) == 1
    sent = mail.outbox[0]
    assert sent.to == [user.email]
    assert "reset-password?token=" in sent.body

    token = sent.body.split("token=")[1].split()[0].strip()
    decoded = verify_password_reset_token(token)
    assert decoded is not None
    assert decoded[0] == str(user.id)


@pytest.mark.django_db
def test_password_reset_email_points_at_the_frontend_not_the_backend(settings):
    settings.BACKEND_BASE_URL = "http://api.example.test"
    settings.FRONTEND_URL = "http://app.example.test"

    user = UserFactory()
    send_password_reset_email(user)

    sent = mail.outbox[0]
    assert "http://app.example.test/reset-password?token=" in sent.body
    assert "api.example.test" not in sent.body


# ==================================================
# request_password_reset
# ==================================================


@pytest.mark.django_db
def test_request_password_reset_sends_email_for_existing_active_user():
    user = UserFactory()
    request_password_reset(user.email)
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == [user.email]


@pytest.mark.django_db
def test_request_password_reset_is_case_insensitive():
    user = UserFactory(email="someone@example.com")
    request_password_reset("SOMEONE@EXAMPLE.COM")
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == [user.email]


@pytest.mark.django_db
def test_request_password_reset_silently_no_ops_for_unknown_email():
    request_password_reset("nobody@example.com")
    assert len(mail.outbox) == 0


@pytest.mark.django_db
def test_request_password_reset_does_not_email_inactive_unverified_user():
    UserFactory(email="unverified@example.com", is_active=False)
    request_password_reset("unverified@example.com")
    assert len(mail.outbox) == 0


@pytest.mark.django_db
def test_request_password_reset_survives_email_send_failure(caplog):
    user = UserFactory()
    with patch(
        "apps.users.services.send_password_reset_email",
        side_effect=RuntimeError("SMTP is down"),
    ), caplog.at_level("ERROR"):
        request_password_reset(user.email)

    assert len(mail.outbox) == 0
    assert "Failed to send password reset email" in caplog.text


# ==================================================
# reset_password
# ==================================================


@pytest.mark.django_db
def test_reset_password_changes_password_with_a_valid_token():
    user = UserFactory()
    user.set_password("original-strong-pass-1")
    user.save()
    token = generate_password_reset_token(user)

    result = reset_password(token, "a-new-strong-pass-2")

    assert result is True
    user.refresh_from_db()
    assert user.check_password("a-new-strong-pass-2")
    assert not user.check_password("original-strong-pass-1")


@pytest.mark.django_db
def test_reset_password_bumps_last_updated():
    user = UserFactory()
    original_last_updated = user.last_updated
    token = generate_password_reset_token(user)

    reset_password(token, "a-new-strong-pass-2")

    user.refresh_from_db()
    assert user.last_updated > original_last_updated


@pytest.mark.django_db
def test_reset_password_token_is_single_use():
    user = UserFactory()
    token = generate_password_reset_token(user)

    first = reset_password(token, "first-new-strong-pass-1")
    assert first is True

    second = reset_password(token, "second-new-strong-pass-2")
    assert second is False

    user.refresh_from_db()
    assert user.check_password("first-new-strong-pass-1")


@pytest.mark.django_db
def test_reset_password_invalid_token_returns_false():
    assert reset_password("garbage-token", "a-new-strong-pass-2") is False


@pytest.mark.django_db
def test_reset_password_token_for_deleted_user_returns_false():
    user = UserFactory()
    token = generate_password_reset_token(user)
    user_id = user.id
    user.delete()

    assert reset_password(token, "a-new-strong-pass-2") is False
    assert not User.objects.filter(id=user_id).exists()
