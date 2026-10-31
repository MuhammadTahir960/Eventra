import threading
import time
import uuid
from functools import partial
from unittest.mock import MagicMock, patch

import pytest
from django.core import mail
from django.db import OperationalError, connection
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.token_blacklist.models import (
    BlacklistedToken,
)
from rest_framework_simplejwt.tokens import RefreshToken

from apps.bookings.factories import BookingFactory
from apps.bookings.models import Booking
from apps.bookings.services import create_booking_from_hold
from apps.common.constants import Roles
from apps.events.factories import EventFactory
from apps.events.models import Event
from apps.payouts.factories import OrganizerPayoutFactory
from apps.payouts.models import OrganizerPayout
from apps.seating.factories import EventSeatFactory, SeatHoldFactory
from apps.seating.models import EventSeat
from apps.tickets.models import Ticket
from apps.users.tokens import (
    verify_password_reset_token,
    verify_token,
)

from ..factories import UserFactory
from ..models import User
from ..serializers import RegisterSerializer
from ..services import (
    AccountDeletionBlockedError,
    IncorrectPasswordError,
    delete_account,
    issue_ws_ticket,
    register_user,
    request_password_reset,
    reset_password,
    send_password_reset_email,
    send_verification_email,
    validate_and_consume_ws_ticket,
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
    assert "/verify-email?token=" in sent.body

    token = sent.body.split("token=")[1].strip()

    assert verify_token(token) == str(user.id)


@pytest.mark.django_db
def test_verification_email_link_points_at_the_frontend_page(settings):
    settings.BACKEND_BASE_URL = "http://api.example.test"
    settings.FRONTEND_URL = "http://app.example.test"

    user = UserFactory(is_active=False)
    send_verification_email(user)

    sent = mail.outbox[0]
    assert "http://app.example.test/verify-email?token=" in sent.body
    assert "api.example.test" not in sent.body


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
            "gender": "other",
            "role": "attendee",
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
            "gender": "other",
            "role": "attendee",
        }
    )
    assert serializer.is_valid(), serializer.errors

    with patch(
        "apps.users.tasks.send_verification_email",
        side_effect=RuntimeError("SMTP is down"),
    ), caplog.at_level("ERROR"):
        user = register_user(serializer)

    assert user.pk is not None
    assert User.objects.filter(email="resilient@example.com").exists()
    assert len(mail.outbox) == 0
    assert "on_commit" in caplog.text


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
        "apps.users.tasks.send_password_reset_email",
        side_effect=RuntimeError("SMTP is down"),
    ), caplog.at_level("ERROR"):
        request_password_reset(user.email)

    assert len(mail.outbox) == 0
    assert "Failed to enqueue password reset" in caplog.text


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


# ==================================================
# WebSocket ticket issuance & consumption
# ==================================================


@pytest.mark.django_db
def test_issue_ws_ticket_returns_opaque_ticket_and_expiry():
    user = UserFactory()
    ticket, expires_at = issue_ws_ticket(user)

    assert isinstance(ticket, str)
    assert len(ticket) > 20
    assert expires_at > timezone.now()


@pytest.mark.django_db
def test_ws_ticket_round_trip_returns_owning_user_id():
    user = UserFactory()
    ticket, _ = issue_ws_ticket(user)

    resolved_user_id = validate_and_consume_ws_ticket(ticket)

    assert resolved_user_id == user.id


@pytest.mark.django_db
def test_ws_ticket_is_single_use():
    user = UserFactory()
    ticket, _ = issue_ws_ticket(user)

    first = validate_and_consume_ws_ticket(ticket)
    second = validate_and_consume_ws_ticket(ticket)

    assert first == user.id
    assert second is None


@pytest.mark.django_db
def test_ws_ticket_expires_after_ttl(monkeypatch):
    import apps.users.services as services_module

    monkeypatch.setattr(services_module, "WS_TICKET_TTL_SECONDS", 1)

    user = UserFactory()
    ticket, _ = issue_ws_ticket(user)

    time.sleep(1.5)

    assert validate_and_consume_ws_ticket(ticket) is None


@pytest.mark.django_db
def test_ws_ticket_garbage_or_unknown_value_returns_none():
    assert validate_and_consume_ws_ticket("this-was-never-issued") is None


@pytest.mark.django_db
def test_ws_ticket_empty_or_missing_value_returns_none():
    assert validate_and_consume_ws_ticket("") is None
    assert validate_and_consume_ws_ticket(None) is None


@pytest.mark.django_db
def test_ws_ticket_two_concurrent_consumers_only_one_wins():
    user = UserFactory()
    ticket, _ = issue_ws_ticket(user)

    results = []
    barrier = threading.Barrier(2)

    def attempt():
        barrier.wait()
        results.append(validate_and_consume_ws_ticket(ticket))

    threads = [threading.Thread(target=attempt) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    winners = [r for r in results if r is not None]
    assert winners == [user.id]
    assert results.count(None) == 1


@pytest.mark.django_db
class TestPasswordResetHardening:
    def test_reset_kills_previously_issued_refresh_tokens(self):
        user = UserFactory()
        refresh = RefreshToken.for_user(user)
        token = generate_password_reset_token(user)

        assert reset_password(token, "a-brand-new-Passw0rd!") is True

        assert BlacklistedToken.objects.filter(token__jti=refresh["jti"]).exists()
        response = APIClient().post(
            "/auth/refresh/", {"refresh": str(refresh)}, format="json"
        )
        assert response.status_code == 401

    def test_reset_link_is_single_use(self):
        user = UserFactory()
        token = generate_password_reset_token(user)
        assert reset_password(token, "a-brand-new-Passw0rd!") is True
        assert reset_password(token, "another-Passw0rd-2!") is False

    def test_reset_email_is_sent_via_the_task_queue(self):
        user = UserFactory()
        request_password_reset(user.email)
        assert len(mail.outbox) == 1
        assert "reset-password?token=" in mail.outbox[0].body
        assert user.password not in mail.outbox[0].body


# ==================================================
# Account deletion and its blockers
# ==================================================

PASSWORD = "testpass123"


def _ticket(user, event, status=Booking.Status.CONFIRMED):
    booking = BookingFactory(user=user, status=status)
    seat = EventSeatFactory(event=event, status=EventSeat.Status.BOOKED)
    Ticket.objects.create(booking=booking, event_seat=seat, status=Ticket.Status.VALID)
    return booking


def _reasons(user):
    with pytest.raises(AccountDeletionBlockedError) as exc:
        delete_account(user, PASSWORD)
    return " ".join(exc.value.reasons)


@pytest.mark.django_db
def test_wipes_personal_data_and_signs_out_everywhere(
    monkeypatch, django_capture_on_commit_callbacks
):
    task = MagicMock()
    monkeypatch.setattr("apps.users.tasks.send_account_deleted_email_task", task)
    user = UserFactory()
    email = user.email
    refresh = RefreshToken.for_user(user)
    hold = SeatHoldFactory(user=user)

    with django_capture_on_commit_callbacks(execute=True):
        delete_account(user, PASSWORD)

    user.refresh_from_db()
    assert user.email == f"deleted-{user.id}@deleted.eventra.invalid"
    assert (user.first_name, user.last_name, user.gender) == ("Deleted", "user", "")
    assert not user.is_active and not user.has_usable_password()
    assert user.deleted_at is not None
    assert BlacklistedToken.objects.filter(token__jti=refresh["jti"]).exists()
    hold.refresh_from_db()
    assert hold.expires_at < timezone.now()
    task.delay.assert_called_once()
    assert task.delay.call_args[0][0] == email
    assert not User.objects.filter(email=email).exists()


@pytest.mark.django_db
def test_wrong_password_changes_nothing():
    user = UserFactory()
    with pytest.raises(IncorrectPasswordError):
        delete_account(user, "not-it")
    user.refresh_from_db()
    assert user.is_active and user.deleted_at is None


@pytest.mark.django_db
def test_attendee_with_tickets_for_an_upcoming_event_is_blocked_until_it_passes():
    user = UserFactory()
    event = EventFactory(status=Event.Status.APPROVED)
    _ticket(user, event)
    assert "haven't happened yet" in _reasons(user)

    Event.all_objects.filter(pk=event.pk).update(
        status=Event.Status.COMPLETED, completed_at=timezone.now()
    )
    delete_account(user, PASSWORD)


@pytest.mark.django_db
def test_checkout_in_progress_and_unfinished_refund_block_deletion():
    user = UserFactory()
    BookingFactory(user=user, status=Booking.Status.PENDING)
    BookingFactory(user=user, status=Booking.Status.REFUND_FAILED)
    reasons = _reasons(user)
    assert "checkout in progress" in reasons
    assert "refund to you" in reasons


@pytest.mark.django_db
def test_organizer_with_unfinished_or_unpaid_events_is_blocked():
    user = UserFactory(role=Roles.ORGANIZER)
    EventFactory(organizer=user, status=Event.Status.PENDING_APPROVAL)
    unpaid = EventFactory(organizer=user, status=Event.Status.COMPLETED)
    _ticket(UserFactory(), unpaid)
    reasons = _reasons(user)
    assert "on sale or in review" in reasons
    assert "haven't been paid out" in reasons


@pytest.mark.django_db
def test_organizer_whose_events_are_all_settled_can_leave():
    user = UserFactory(role=Roles.ORGANIZER)
    paid = EventFactory(organizer=user, status=Event.Status.COMPLETED)
    _ticket(UserFactory(), paid)
    OrganizerPayoutFactory(event=paid, status=OrganizerPayout.Status.SETTLED)
    EventFactory(organizer=user, status=Event.Status.REJECTED)
    delete_account(user, PASSWORD)


@pytest.mark.django_db
def test_organizer_with_refunds_still_running_is_blocked():
    user = UserFactory(role=Roles.ORGANIZER)
    cancelled = EventFactory(organizer=user, status=Event.Status.CANCELLED)
    _ticket(UserFactory(), cancelled, status=Booking.Status.REFUND_FAILED)
    assert "still in progress" in _reasons(user)


@pytest.mark.django_db
def test_the_last_admin_cannot_leave_but_one_of_two_can():
    admin = UserFactory(role=Roles.ADMIN)
    assert "only admin" in _reasons(admin)
    UserFactory(role=Roles.ADMIN)
    delete_account(admin, PASSWORD)


@pytest.mark.django_db
def test_a_refund_still_pending_on_a_cancelled_event_blocks_deletion():
    user = UserFactory()
    _ticket(user, EventFactory(status=Event.Status.CANCELLED))
    assert "refund to you" in _reasons(user)


def _race(*calls):
    barrier, errors = threading.Barrier(len(calls)), []

    def run(call):
        barrier.wait()
        try:
            call()
        except OperationalError as exc:
            errors.append(exc)
        except Exception:
            pass
        finally:
            connection.close()

    threads = [threading.Thread(target=run, args=(call,)) for call in calls]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []


@pytest.mark.django_db(transaction=True)
def test_deleting_while_booking_neither_deadlocks_nor_strands_a_booking(monkeypatch):
    monkeypatch.setattr("apps.users.tasks.send_account_deleted_email_task", MagicMock())
    for _ in range(5):
        user = UserFactory()
        hold = SeatHoldFactory(user=user)
        _race(
            partial(delete_account, user, PASSWORD),
            partial(create_booking_from_hold, hold.group_id, user),
        )
        user.refresh_from_db()
        pending = Booking.objects.filter(user=user, status=Booking.Status.PENDING)
        assert not (user.deleted_at and pending.exists())


@pytest.mark.django_db(transaction=True)
def test_the_last_two_admins_leaving_together_leaves_one(monkeypatch):
    monkeypatch.setattr("apps.users.tasks.send_account_deleted_email_task", MagicMock())
    User.objects.filter(role=Roles.ADMIN).update(is_active=False)
    first, second = UserFactory(role=Roles.ADMIN), UserFactory(role=Roles.ADMIN)
    _race(
        partial(delete_account, first, PASSWORD),
        partial(delete_account, second, PASSWORD),
    )
    assert User.objects.filter(role=Roles.ADMIN, is_active=True).count() == 1
