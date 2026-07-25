import pytest
from django.core import mail
from apps.users.factories import UserFactory
from apps.users.serializers import RegisterSerializer
from apps.users.services import (
    register_user,
    send_verification_email,
    verify_user_email,
)
from apps.users.tokens import generate_verification_token


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
    assert "verify-email?token=" in sent.body

    token = sent.body.split("token=")[1].strip()
    from apps.users.tokens import verify_token

    assert verify_token(token) == user.id


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
    token = generate_verification_token(999_999)
    assert verify_user_email(token) is None
