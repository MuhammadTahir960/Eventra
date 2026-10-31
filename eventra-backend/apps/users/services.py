import logging
import secrets
import uuid
from datetime import datetime, timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.db import models, transaction
from django.utils import timezone
from django.utils.crypto import constant_time_compare
from rest_framework_simplejwt.token_blacklist.models import (
    BlacklistedToken,
    OutstandingToken,
)

from apps.bookings.models import Booking
from apps.common.constants import Roles
from apps.common.redis import get_redis_client
from apps.events.models import Event
from apps.payouts.models import OrganizerPayout
from apps.seating.models import SeatHold

from .models import User
from .tokens import (
    generate_password_reset_token,
    generate_verification_token,
    password_fingerprint,
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
    verification_link = f"{settings.FRONTEND_URL}/verify-email?token={token}"

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

    from .tasks import send_verification_email_task

    with transaction.atomic():
        user = serializer.save()
        transaction.on_commit(
            lambda: send_verification_email_task.delay(str(user.id)), robust=True
        )
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
    from .tasks import send_password_reset_email_task

    user = User.objects.filter(email__iexact=email.strip(), is_active=True).first()
    if user is None:
        return

    try:
        send_password_reset_email_task.delay(str(user.id))
    except Exception as exc:
        logger.error("Failed to enqueue password reset for user %s: %s", user.id, exc)


def reset_password(token: str, new_password: str) -> bool:
    decoded = verify_password_reset_token(token)
    if decoded is None:
        return False
    user_id, fingerprint_at_issue = decoded

    with transaction.atomic():
        try:
            user = User.objects.select_for_update().get(id=user_id)
        except User.DoesNotExist:
            return False

        if not constant_time_compare(fingerprint_at_issue, password_fingerprint(user)):
            return False

        user.set_password(new_password)
        user.save(update_fields=["password", "last_updated"])

        for outstanding in OutstandingToken.objects.filter(user=user):
            BlacklistedToken.objects.get_or_create(token=outstanding)
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
        # a link sent before the account was deleted must not bring it back
        if user.deleted_at is not None:
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


class IncorrectPasswordError(Exception):
    """Raised when the password given to confirm account deletion is wrong."""


class AccountDeletionBlockedError(Exception):
    """Raised when the account still has tickets, events or money in flight."""

    def __init__(self, reasons: list[str]):
        self.reasons = reasons
        super().__init__(" ".join(reasons))


_UNFINISHED_EVENT_STATUSES = (Event.Status.APPROVED, Event.Status.PENDING_APPROVAL)


def account_deletion_blockers(user: User) -> list[str]:
    reasons = []
    bookings = Booking.objects.filter(user=user)
    if bookings.filter(
        status=Booking.Status.CONFIRMED,
        tickets__event_seat__event__status__in=_UNFINISHED_EVENT_STATUSES,
    ).exists():
        reasons.append(
            "You have tickets for events that haven't happened yet. "
            "You can delete your account once they have passed."
        )
    if bookings.filter(status=Booking.Status.PENDING).exists():
        reasons.append(
            "You have a checkout in progress. Finish it, or wait a few minutes "
            "for it to expire."
        )
    if bookings.filter(
        models.Q(status=Booking.Status.REFUND_FAILED)
        | models.Q(
            status=Booking.Status.CONFIRMED,
            tickets__event_seat__event__status=Event.Status.CANCELLED,
        )
    ).exists():
        reasons.append("A refund to you is still being processed.")

    events = Event.all_objects.filter(organizer=user)
    if events.filter(status__in=_UNFINISHED_EVENT_STATUSES).exists():
        reasons.append(
            "You have events that are on sale or in review. Cancel them, or wait "
            "until they have finished and been paid out."
        )
    sold = Booking.objects.filter(
        tickets__event_seat__event=models.OuterRef("pk"),
        status=Booking.Status.CONFIRMED,
    )
    settled = OrganizerPayout.objects.filter(
        event=models.OuterRef("pk"), status=OrganizerPayout.Status.SETTLED
    )
    if (
        events.filter(status=Event.Status.COMPLETED)
        .filter(models.Exists(sold), ~models.Exists(settled))
        .exists()
    ):
        reasons.append("You have completed events that haven't been paid out yet.")
    if Booking.objects.filter(
        tickets__event_seat__event__in=events.filter(status=Event.Status.CANCELLED),
        status__in=(Booking.Status.CONFIRMED, Booking.Status.REFUND_FAILED),
    ).exists():
        reasons.append("Refunds for a cancelled event of yours are still in progress.")

    if (
        user.role == Roles.ADMIN
        and not User.objects.filter(role=Roles.ADMIN, is_active=True)
        .exclude(pk=user.pk)
        .exists()
    ):
        reasons.append("You're the only admin. Make someone else an admin first.")
    return reasons


def delete_account(user: User, password: str) -> None:
    """Wipes personal data and signs the user out everywhere; money records stay."""
    with transaction.atomic():
        locked = User.objects.select_for_update(no_key=True)
        if user.role == Roles.ADMIN:
            list(locked.filter(role=Roles.ADMIN, is_active=True).order_by("id"))
        user = locked.get(pk=user.pk)
        if not user.check_password(password):
            raise IncorrectPasswordError()

        SeatHold.objects.filter(user=user).update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )
        reasons = account_deletion_blockers(user)
        if reasons:
            raise AccountDeletionBlockedError(reasons)

        original_email, first_name = user.email, user.first_name
        user.email = f"deleted-{user.id}@deleted.eventra.invalid"
        user.first_name, user.last_name, user.gender = "Deleted", "user", ""
        user.set_unusable_password()
        user.is_active = False
        user.is_email_verified = False
        user.deleted_at = timezone.now()
        user.save()

        BlacklistedToken.objects.bulk_create(
            [
                BlacklistedToken(token=outstanding)
                for outstanding in OutstandingToken.objects.filter(user=user)
            ],
            ignore_conflicts=True,
        )

        from .tasks import send_account_deleted_email_task

        transaction.on_commit(
            lambda: send_account_deleted_email_task.delay(original_email, first_name),
            robust=True,
        )


def send_account_deleted_email(email: str, first_name: str) -> None:
    send_mail(
        subject="Your Eventra account has been deleted",
        message=(
            f"Hi {first_name},\n\n"
            "Your Eventra account has been deleted and your personal details "
            "removed. Records of past payments are kept.\n\n"
            "You can sign up again with this email address at any time."
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[email],
        fail_silently=False,
    )
