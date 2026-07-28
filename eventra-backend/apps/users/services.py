from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from .models import User
from .tokens import generate_verification_token, verify_token
import logging

logger = logging.getLogger(__name__)


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
        user.save(update_fields=["is_active", "is_email_verified"])
        return user, True
