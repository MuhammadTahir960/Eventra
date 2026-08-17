import logging
import secrets
import uuid
from datetime import datetime, timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from apps.common.redis import get_redis_client

from .models import User
from .tokens import (
    generate_password_reset_token,
    generate_verification_token,
    verify_password_reset_token,
    verify_token,
)

logger = logging.getLogger(__name__)

WS_TICKET_TTL_SECONDS = 30
_WS_TICKET_KEY_PREFIX = "ws_ticket:"


def send_verification_email(user: User) -> None:
    """
    Builds the verification link and sends it through Django's configured
    EMAIL_BACKEND. In dev this is the console backend — the "email" just
    prints to your terminal, no real SMTP involved.
    """
    token = generate_verification_token(user.id)
    verification_link = f"{settings.BACKEND_BASE_URL}/auth/verify-email/?token={token}"

    send_mail(
        subject="Verify your Eventra account",
        message=f"Welcome to Eventra! Verify your email:\n\n{verification_link}",
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=False,
    )


def register_user(serializer) -> User:
    """
    Thin orchestration: save the user then queue the verification email.

    An email, once sent, can't be rolled back the way a DB write can.
    Wrapping the send in on_commit means it only actually fires once this
    transaction has fully and successfully committed. Any delivery error
    is caught and logged so post-commit failures do not crash the request.
    """

    def _safe_send():
        try:
            send_verification_email(user)
        except Exception as exc:
            logger.error(
                "Failed to send verification email for user %s: %s", user.id, exc
            )

    with transaction.atomic():
        user = serializer.save()
        transaction.on_commit(_safe_send)
    return user


def send_password_reset_email(user: User) -> None:
    token = generate_password_reset_token(user)
    reset_link = f"{settings.FRONTEND_URL}/reset-password?token={token}"

    send_mail(
        subject="Reset your Eventra password",
        message=(
            "Use this link to reset your password:\n\n"
            f"{reset_link}\n\n"
            "This link expires in 1 hour. If you didn't request this, "
            "you can safely ignore this email."
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=False,
    )


def request_password_reset(email: str) -> None:
    user = User.objects.filter(email__iexact=email.strip(), is_active=True).first()
    if user is None:
        return

    try:
        send_password_reset_email(user)
    except Exception as exc:
        logger.error(
            "Failed to send password reset email for user %s: %s", user.id, exc
        )


def reset_password(token: str, new_password: str) -> bool:
    decoded = verify_password_reset_token(token)
    if decoded is None:
        return False
    user_id, password_hash_at_issue = decoded

    with transaction.atomic():
        try:
            user = User.objects.select_for_update().get(id=user_id)
        except User.DoesNotExist:
            return False

        if user.password != password_hash_at_issue:
            return False

        user.set_password(new_password)
        user.save(update_fields=["password", "last_updated"])
        return True


def verify_user_email(token: str) -> tuple[User, bool] | None:
    """
    Consumes a verification token. Returns (user, was_newly_verified) on
    success — was_newly_verified is False if the email was already
    verified before this call, letting the view distinguish "just verified"
    from "already verified" without a second DB query. Returns None if the
    token is invalid/expired/points to a user that no longer exists.
    """
    user_id = verify_token(token)
    if user_id is None:
        return None

    with transaction.atomic():
        try:
            user = User.objects.select_for_update().get(id=user_id)
        except User.DoesNotExist:
            return None

        if user.is_email_verified:
            # Valid token, but this account was already verified — not an
            # error, just nothing new to do. The view surfaces this
            # distinctly rather than claiming a fresh verification just
            # happened.
            return user, False

        # Only activate the account as part of first-time verification.
        user.is_active = True
        user.is_email_verified = True
        user.save(update_fields=["is_active", "is_email_verified", "last_updated"])
        return user, True


def issue_ws_ticket(user: User) -> tuple[str, datetime]:
    """Issue a single-use, ~30-second WebSocket connection ticket for `user`."""
    ticket = secrets.token_urlsafe(32)
    expires_at = timezone.now() + timedelta(seconds=WS_TICKET_TTL_SECONDS)

    client = get_redis_client()
    client.set(
        f"{_WS_TICKET_KEY_PREFIX}{ticket}",
        str(user.id),
        ex=WS_TICKET_TTL_SECONDS,
    )
    return ticket, expires_at


def validate_and_consume_ws_ticket(ticket: str) -> uuid.UUID | None:
    """
    Atomically look up and invalidate a WebSocket ticket in one Redis round
    trip (GETDEL) — the ticket is gone the instant it's read, valid or not,
    so it can never be replayed no matter what the caller does with the
    result afterward. Returns the owning user's id on success, or None if
    the ticket is missing, expired, or already used.
    """
    if not ticket:
        return None

    client = get_redis_client()
    raw_user_id = client.getdel(f"{_WS_TICKET_KEY_PREFIX}{ticket}")
    if raw_user_id is None:
        return None

    try:
        return uuid.UUID(raw_user_id.decode("utf-8"))
    except (ValueError, AttributeError, TypeError):
        return None
