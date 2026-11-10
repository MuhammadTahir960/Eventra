import threading
import uuid
from datetime import timedelta
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
import stripe
from django.db import IntegrityError, connection
from django.utils import timezone

from apps.events.factories import EventFactory, TicketTierFactory
from apps.events.models import Event
from apps.payments.factories import PaymentFactory
from apps.seating.factories import EventSeatFactory, SeatHoldFactory
from apps.seating.models import EventSeat, SeatHold
from apps.users.factories import UserFactory
from tests.helpers import paid_booking, unpaid_booking

from ..factories import BookingFactory
from ..models import Booking
from ..services import (
    BOOKING_EXPIRY_MINUTES,
    BookingExpiredError,
    BookingNotPendingError,
    EventClosedError,
    HoldExpiredError,
    HoldNotFoundError,
    checkout_booking,
    create_booking_from_hold,
    release_pending_bookings_for_event,
    sweep_expired_pending_bookings,
)

pytestmark = pytest.mark.django_db


def _held_seat_with_hold(user, event=None, price=Decimal("25.00"), group_id=None):
    event = event or EventFactory(status="approved")
    group_id = group_id or uuid.uuid4()
    seat = EventSeatFactory(
        event=event, status=EventSeat.Status.HELD, price_override=price
    )
    SeatHoldFactory(
        group_id=group_id,
        event_seat=seat,
        user=user,
        expires_at=timezone.now() + timedelta(minutes=10),
    )
    return group_id, seat


class TestCreateBookingFromHold:
    def test_creates_pending_booking_with_correct_total(self):
        user = UserFactory()
        group_id, seat = _held_seat_with_hold(user, price=Decimal("25.00"))

        booking, created = create_booking_from_hold(group_id, user)

        assert created is True
        assert booking.status == Booking.Status.PENDING
        assert booking.total_amount == Decimal("25.00")
        assert booking.source_hold_group_id == group_id

    def test_records_each_seat_with_its_price_and_totals_them(self):
        user = UserFactory()
        event = EventFactory(status="approved")
        group_id, cheap = _held_seat_with_hold(user, event=event, price=Decimal("20"))
        _, dear = _held_seat_with_hold(
            user, event=event, price=Decimal("35.50"), group_id=group_id
        )

        booking, _ = create_booking_from_hold(group_id, user)

        items = {item.event_seat_id: item for item in booking.tickets.all()}
        assert items.keys() == {cheap.id, dear.id}
        assert items[cheap.id].price == Decimal("20.00")
        assert items[dear.id].price == Decimal("35.50")
        assert {item.event_seat.event_id for item in items.values()} == {event.id}
        assert booking.total_amount == Decimal("55.50")

    def test_replay_adds_no_duplicate_items(self):
        user = UserFactory()
        group_id, _ = _held_seat_with_hold(user)

        booking, _ = create_booking_from_hold(group_id, user)
        create_booking_from_hold(group_id, user)

        assert booking.tickets.count() == 1

    def test_items_outlive_the_seat_link_when_a_booking_expires(self):
        user = UserFactory()
        group_id, seat = _held_seat_with_hold(user)
        booking, _ = create_booking_from_hold(group_id, user)
        Booking.objects.filter(pk=booking.pk).update(
            created_at=timezone.now() - timedelta(hours=1)
        )

        sweep_expired_pending_bookings()

        seat.refresh_from_db()
        assert not booking.held_seats().filter(id=seat.id).exists()
        assert booking.tickets.get().event_seat_id == seat.id

    def test_deletes_the_hold_group_and_leaves_seat_held(self):
        user = UserFactory()
        group_id, seat = _held_seat_with_hold(user)

        create_booking_from_hold(group_id, user)

        assert not SeatHold.objects.filter(group_id=group_id).exists()
        seat.refresh_from_db()
        assert seat.status == EventSeat.Status.HELD

    def test_replayed_call_returns_existing_booking_not_a_duplicate(self):
        user = UserFactory()
        group_id, seat = _held_seat_with_hold(user)

        first_booking, first_created = create_booking_from_hold(group_id, user)
        second_booking, second_created = create_booking_from_hold(group_id, user)

        assert first_created is True
        assert second_created is False
        assert first_booking.id == second_booking.id
        assert Booking.objects.filter(source_hold_group_id=group_id).count() == 1

    def test_unknown_hold_id_raises_not_found(self):
        user = UserFactory()
        with pytest.raises(HoldNotFoundError):
            create_booking_from_hold(uuid.uuid4(), user)

    def test_another_users_hold_raises_not_found(self):
        owner = UserFactory()
        stranger = UserFactory()
        group_id, _ = _held_seat_with_hold(owner)

        with pytest.raises(HoldNotFoundError):
            create_booking_from_hold(group_id, stranger)

    def test_expired_hold_raises_conflict(self):
        user = UserFactory()
        event = EventFactory(status="approved")
        group_id = uuid.uuid4()
        seat = EventSeatFactory(event=event, status=EventSeat.Status.HELD)
        SeatHoldFactory(
            group_id=group_id,
            event_seat=seat,
            user=user,
            expires_at=timezone.now() - timedelta(seconds=1),
        )

        with pytest.raises(HoldExpiredError):
            create_booking_from_hold(group_id, user)

    def test_multi_seat_hold_sums_correctly(self):
        user = UserFactory()
        event = EventFactory(status="approved")
        group_id = uuid.uuid4()
        for price in (Decimal("25.00"), Decimal("40.00"), Decimal("15.50")):
            seat = EventSeatFactory(
                event=event, status=EventSeat.Status.HELD, price_override=price
            )
            SeatHoldFactory(
                group_id=group_id,
                event_seat=seat,
                user=user,
                expires_at=timezone.now() + timedelta(minutes=10),
            )

        booking, created = create_booking_from_hold(group_id, user)

        assert booking.total_amount == Decimal("80.50")

    @pytest.mark.django_db(transaction=True)
    def test_concurrent_retry_backstop_yields_exactly_one_booking(self):
        user = UserFactory()
        group_id, seat = _held_seat_with_hold(user)

        results = []
        barrier = threading.Barrier(2)

        errors = []

        def attempt():
            barrier.wait()
            try:
                booking, created = create_booking_from_hold(group_id, user)
                results.append((booking.id, created))
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)
            finally:
                connection.close()

        threads = [threading.Thread(target=attempt) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
        assert Booking.objects.filter(source_hold_group_id=group_id).count() == 1
        assert len(results) == 2
        assert len({r[0] for r in results}) == 1
        assert sorted(r[1] for r in results) == [False, True]
        winner = Booking.objects.get(id=results[0][0])
        assert winner.held_seats().filter(id=seat.id).exists()

    @pytest.mark.django_db(transaction=True)
    def test_integrity_error_backstop_returns_the_winning_booking(self, monkeypatch):
        user = UserFactory()
        group_id, seat = _held_seat_with_hold(user)

        winner_holder = {}
        real_create = Booking.objects.create

        def _raise_after_concurrent_commit(*args, **kwargs):
            def _commit_winner():
                winner_holder["booking"] = real_create(
                    user=user,
                    status=Booking.Status.PENDING,
                    source_hold_group_id=group_id,
                )
                connection.close()

            t = threading.Thread(target=_commit_winner)
            t.start()
            t.join()
            raise IntegrityError("duplicate key value violates unique constraint")

        monkeypatch.setattr(Booking.objects, "create", _raise_after_concurrent_commit)

        booking, created = create_booking_from_hold(group_id, user)

        monkeypatch.setattr(Booking.objects, "create", real_create)

        assert booking.id == winner_holder["booking"].id
        assert created is False


class TestCheckoutBooking:
    def test_raises_when_booking_not_pending(self):
        booking = BookingFactory(status=Booking.Status.CANCELLED)
        with pytest.raises(BookingNotPendingError):
            checkout_booking(booking)

    def test_refuses_an_expired_booking_without_calling_stripe(self, monkeypatch):
        create = MagicMock()
        monkeypatch.setattr(
            "apps.payments.services.stripe.PaymentIntent.create", create
        )
        booking = BookingFactory(status=Booking.Status.PENDING)
        Booking.objects.filter(pk=booking.pk).update(
            created_at=timezone.now() - timedelta(minutes=BOOKING_EXPIRY_MINUTES + 1)
        )
        booking.refresh_from_db()

        with pytest.raises(BookingExpiredError):
            checkout_booking(booking)
        create.assert_not_called()

    def test_refuses_when_the_event_is_no_longer_on_sale(self, monkeypatch):
        create = MagicMock()
        monkeypatch.setattr(
            "apps.payments.services.stripe.PaymentIntent.create", create
        )
        booking = unpaid_booking(event=EventFactory(status=Event.Status.CANCELLED))

        with pytest.raises(EventClosedError):
            checkout_booking(booking)
        create.assert_not_called()


class TestSweepExpiredPendingBookings:
    def test_stale_pending_booking_is_released_and_cancelled(
        self, monkeypatch, django_capture_on_commit_callbacks
    ):
        mock_notify = MagicMock()
        monkeypatch.setattr(
            "apps.seating.services.notify_internal_broadcast", mock_notify
        )

        user = UserFactory()
        group_id, seat = _held_seat_with_hold(user)
        booking, _ = create_booking_from_hold(group_id, user)
        Booking.objects.filter(id=booking.id).update(
            created_at=timezone.now() - timedelta(minutes=10)
        )

        with django_capture_on_commit_callbacks(execute=True):
            sweep_expired_pending_bookings()

        booking.refresh_from_db()
        seat.refresh_from_db()
        assert booking.status == Booking.Status.CANCELLED
        assert seat.status == EventSeat.Status.AVAILABLE
        assert not booking.held_seats().filter(id=seat.id).exists()
        mock_notify.assert_called_once()
        _, kwargs = mock_notify.call_args
        assert kwargs["seat_ids"] == [seat.id]
        assert kwargs["status_label"] == "available"

    def test_booking_still_within_window_is_left_alone(self, monkeypatch):
        mock_notify = MagicMock()
        monkeypatch.setattr(
            "apps.seating.services.notify_internal_broadcast", mock_notify
        )

        user = UserFactory()
        group_id, seat = _held_seat_with_hold(user)
        booking, _ = create_booking_from_hold(group_id, user)

        sweep_expired_pending_bookings()

        booking.refresh_from_db()
        seat.refresh_from_db()
        assert booking.status == Booking.Status.PENDING
        assert seat.status == EventSeat.Status.HELD
        mock_notify.assert_not_called()

    def test_already_confirmed_booking_is_untouched_even_if_stale(self, monkeypatch):
        mock_notify = MagicMock()
        monkeypatch.setattr(
            "apps.seating.services.notify_internal_broadcast", mock_notify
        )

        user = UserFactory()
        group_id, seat = _held_seat_with_hold(user)
        booking, _ = create_booking_from_hold(group_id, user)
        Booking.objects.filter(id=booking.id).update(
            status=Booking.Status.CONFIRMED,
            created_at=timezone.now() - timedelta(minutes=10),
        )

        sweep_expired_pending_bookings()

        booking.refresh_from_db()
        assert booking.status == Booking.Status.CONFIRMED
        mock_notify.assert_not_called()

    def test_multiple_stale_bookings_across_different_events_each_broadcast(
        self, monkeypatch, django_capture_on_commit_callbacks
    ):
        mock_notify = MagicMock()
        monkeypatch.setattr(
            "apps.seating.services.notify_internal_broadcast", mock_notify
        )

        user = UserFactory()
        group_id_a, seat_a = _held_seat_with_hold(user)
        booking_a, _ = create_booking_from_hold(group_id_a, user)
        group_id_b, seat_b = _held_seat_with_hold(user)
        booking_b, _ = create_booking_from_hold(group_id_b, user)
        Booking.objects.filter(id__in=[booking_a.id, booking_b.id]).update(
            created_at=timezone.now() - timedelta(minutes=10)
        )

        with django_capture_on_commit_callbacks(execute=True):
            sweep_expired_pending_bookings()

        assert mock_notify.call_count == 2
        booking_a.refresh_from_db()
        booking_b.refresh_from_db()
        assert booking_a.status == Booking.Status.CANCELLED
        assert booking_b.status == Booking.Status.CANCELLED


class TestReleasePendingBookingsForEvent:
    def test_releases_only_this_users_pending_booking_for_this_event(self):
        user = UserFactory()
        event = EventFactory(status="approved")
        group_id, seat = _held_seat_with_hold(user, event=event)
        mine, _ = create_booking_from_hold(group_id, user)
        other_event_group, _ = _held_seat_with_hold(user)
        other_event, _ = create_booking_from_hold(other_event_group, user)
        stranger = UserFactory()
        stranger_group, _ = _held_seat_with_hold(stranger, event=event)
        theirs, _ = create_booking_from_hold(stranger_group, stranger)

        release_pending_bookings_for_event(user=user, event=event)

        for booking in (mine, other_event, theirs):
            booking.refresh_from_db()
        seat.refresh_from_db()
        assert mine.status == Booking.Status.CANCELLED
        assert seat.status == EventSeat.Status.AVAILABLE
        assert other_event.status == Booking.Status.PENDING
        assert theirs.status == Booking.Status.PENDING

    def test_keeps_a_booking_whose_payment_already_went_through(self, monkeypatch):
        monkeypatch.setattr(
            "apps.payments.services.stripe.PaymentIntent.cancel",
            MagicMock(side_effect=stripe.error.InvalidRequestError("done", "id")),
        )
        monkeypatch.setattr(
            "apps.payments.services.stripe.PaymentIntent.retrieve",
            MagicMock(return_value=MagicMock(status="succeeded")),
        )
        user = UserFactory()
        event = EventFactory(status="approved")
        group_id, seat = _held_seat_with_hold(user, event=event)
        booking, _ = create_booking_from_hold(group_id, user)
        PaymentFactory(booking=booking)

        release_pending_bookings_for_event(user=user, event=event)

        booking.refresh_from_db()
        seat.refresh_from_db()
        assert booking.status == Booking.Status.PENDING
        assert seat.status == EventSeat.Status.HELD


def test_a_booking_knows_its_event_from_its_seats():
    event = EventFactory()
    booking = paid_booking(event, (TicketTierFactory(event=event), "10.00"))
    assert booking.event == event
    assert BookingFactory().event is None
