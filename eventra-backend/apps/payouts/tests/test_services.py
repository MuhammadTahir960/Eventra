import threading
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from django.db import connection

from apps.bookings.factories import BookingFactory
from apps.bookings.models import Booking
from apps.events.factories import EventFactory, TicketTierFactory
from apps.events.models import Event
from apps.seating.factories import EventSeatFactory
from apps.seating.models import EventSeat
from apps.tickets.models import Ticket
from apps.users.factories import UserFactory

from ..factories import OrganizerPayoutFactory
from ..models import OrganizerPayout
from ..services import (
    PLATFORM_FEE_PERCENTAGE,
    PayoutNotSettleableError,
    _sum_confirmed_booking_totals,
    _ticket_sale_amount,
    compute_payout_amounts,
    create_payout,
    create_payouts_for_completed_events,
    get_event_sales,
    request_payout_settlement,
    settle_payout,
)

pytestmark = pytest.mark.django_db


def _confirmed_booking_with_ticket(event, total_amount):
    booking = BookingFactory(status=Booking.Status.CONFIRMED, total_amount=total_amount)
    seat = EventSeatFactory(
        event=event, status=EventSeat.Status.BOOKED, price_override=total_amount
    )
    Ticket.objects.create(booking=booking, event_seat=seat, status=Ticket.Status.VALID)
    return booking


class TestSumConfirmedBookingTotals:
    def test_sums_only_confirmed_bookings(self):
        event = EventFactory(status=Event.Status.COMPLETED)
        _confirmed_booking_with_ticket(event, Decimal("50.00"))
        _confirmed_booking_with_ticket(event, Decimal("30.00"))

        cancelled = BookingFactory(
            status=Booking.Status.CANCELLED, total_amount=Decimal("99.00")
        )
        seat = EventSeatFactory(event=event, status=EventSeat.Status.AVAILABLE)
        Ticket.objects.create(
            booking=cancelled, event_seat=seat, status=Ticket.Status.CANCELLED
        )

        assert _sum_confirmed_booking_totals(event) == Decimal("80.00")

    def test_zero_when_no_confirmed_bookings(self):
        event = EventFactory(status=Event.Status.COMPLETED)
        assert _sum_confirmed_booking_totals(event) == Decimal("0.00")


class TestComputePayoutAmounts:
    def test_platform_fee_is_ten_percent(self):
        event = EventFactory(status=Event.Status.COMPLETED)
        _confirmed_booking_with_ticket(event, Decimal("100.00"))

        gross, fee, net = compute_payout_amounts(event)

        assert gross == Decimal("100.00")
        assert fee == Decimal("100.00") * PLATFORM_FEE_PERCENTAGE
        assert net == gross - fee

    @pytest.mark.parametrize(
        "gross,expected_fee",
        [
            (Decimal("1.25"), Decimal("0.13")),
            (Decimal("9.99"), Decimal("1.00")),
            (Decimal("0.05"), Decimal("0.01")),
        ],
    )
    def test_rounding_boundary_uses_round_half_up(self, gross, expected_fee):
        event = EventFactory(status=Event.Status.COMPLETED)
        _confirmed_booking_with_ticket(event, gross)

        _, fee, _ = compute_payout_amounts(event)

        assert fee == expected_fee


class TestTicketSaleAmount:
    def test_uses_price_override_when_set(self):
        event = EventFactory(status=Event.Status.COMPLETED)
        seat = EventSeatFactory(
            event=event, status=EventSeat.Status.BOOKED, price_override=Decimal("15.00")
        )
        booking = BookingFactory(status=Booking.Status.CONFIRMED)
        ticket = Ticket.objects.create(booking=booking, event_seat=seat)

        assert _ticket_sale_amount(ticket) == Decimal("15.00")

    def test_falls_back_to_ticket_tier_price_when_no_override(self):
        event = EventFactory(status=Event.Status.COMPLETED)
        tier = TicketTierFactory(event=event, price=Decimal("25.00"))
        seat = EventSeatFactory(
            event=event,
            ticket_tier=tier,
            status=EventSeat.Status.BOOKED,
            price_override=None,
        )
        booking = BookingFactory(status=Booking.Status.CONFIRMED)
        ticket = Ticket.objects.create(booking=booking, event_seat=seat)

        assert _ticket_sale_amount(ticket) == Decimal("25.00")


class TestGetEventSales:
    def test_counts_only_confirmed_tickets_and_matches_gross_revenue(self):
        event = EventFactory(status=Event.Status.COMPLETED)
        _confirmed_booking_with_ticket(event, Decimal("40.00"))
        _confirmed_booking_with_ticket(event, Decimal("60.00"))

        sales = get_event_sales(event)

        assert sales["tickets_sold"] == 2
        assert sales["gross_revenue"] == Decimal("100.00")
        assert {t["status"] for t in sales["tickets"]} == {"confirmed"}

    def test_no_sales_returns_zeroed_empty_response(self):
        event = EventFactory(status=Event.Status.COMPLETED)

        sales = get_event_sales(event)

        assert sales == {
            "tickets_sold": 0,
            "gross_revenue": Decimal("0.00"),
            "tickets": [],
        }

    def test_pending_and_cancelled_bookings_never_appear(self):
        event = EventFactory(status=Event.Status.COMPLETED)
        _confirmed_booking_with_ticket(event, Decimal("50.00"))

        for excluded_status in (Booking.Status.PENDING, Booking.Status.CANCELLED):
            excluded_booking = BookingFactory(
                status=excluded_status, total_amount=Decimal("999.00")
            )
            seat = EventSeatFactory(event=event, status=EventSeat.Status.AVAILABLE)
            Ticket.objects.create(booking=excluded_booking, event_seat=seat)

        sales = get_event_sales(event)

        assert sales["tickets_sold"] == 1
        assert sales["gross_revenue"] == Decimal("50.00")

    def test_only_includes_tickets_for_the_requested_event(self):
        event = EventFactory(status=Event.Status.COMPLETED)
        other_event = EventFactory(status=Event.Status.COMPLETED)
        _confirmed_booking_with_ticket(event, Decimal("50.00"))
        _confirmed_booking_with_ticket(other_event, Decimal("500.00"))

        sales = get_event_sales(event)

        assert sales["tickets_sold"] == 1
        assert sales["gross_revenue"] == Decimal("50.00")

    def test_multi_seat_booking_lists_one_entry_per_ticket_and_all_share_the_refund_tag(
        self,
    ):
        event = EventFactory(status=Event.Status.COMPLETED)
        booking = BookingFactory(
            status=Booking.Status.CONFIRMED, total_amount=Decimal("90.00")
        )
        seat_a = EventSeatFactory(
            event=event, status=EventSeat.Status.BOOKED, price_override=Decimal("40.00")
        )
        seat_b = EventSeatFactory(
            event=event, status=EventSeat.Status.BOOKED, price_override=Decimal("50.00")
        )
        ticket_a = Ticket.objects.create(booking=booking, event_seat=seat_a)
        ticket_b = Ticket.objects.create(booking=booking, event_seat=seat_b)

        sales = get_event_sales(event)
        assert sales["tickets_sold"] == 2
        assert sales["gross_revenue"] == Decimal("90.00")
        assert {t["status"] for t in sales["tickets"]} == {"confirmed"}

        booking.status = Booking.Status.REFUNDED
        booking.save(update_fields=["status"])

        sales = get_event_sales(event)
        assert sales["tickets_sold"] == 2
        assert sales["gross_revenue"] == Decimal("0.00")
        entries = {t["ticket_id"]: t for t in sales["tickets"]}
        assert entries[ticket_a.id]["status"] == "refunded"
        assert entries[ticket_b.id]["status"] == "refunded"

    def test_refunded_ticket_stays_in_history_but_is_deducted_and_tagged(self):
        event = EventFactory(status=Event.Status.COMPLETED)
        kept = _confirmed_booking_with_ticket(event, Decimal("40.00"))
        refunded = _confirmed_booking_with_ticket(event, Decimal("60.00"))

        refunded.status = Booking.Status.REFUNDED
        refunded.save(update_fields=["status"])

        sales = get_event_sales(event)

        assert sales["tickets_sold"] == 2
        assert sales["gross_revenue"] == Decimal("40.00")

        by_status = {t["status"] for t in sales["tickets"]}
        assert by_status == {"confirmed", "refunded"}

        refunded_ticket_id = refunded.tickets.get().id
        kept_ticket_id = kept.tickets.get().id
        entries = {t["ticket_id"]: t for t in sales["tickets"]}
        assert entries[refunded_ticket_id]["status"] == "refunded"
        assert entries[refunded_ticket_id]["amount"] == Decimal("60.00")
        assert entries[kept_ticket_id]["status"] == "confirmed"
        assert (
            entries[refunded_ticket_id]["ticket_code"]
            == refunded.tickets.get().ticket_code
        )

    def test_refund_failed_booking_still_counts_toward_revenue(self):
        event = EventFactory(status=Event.Status.COMPLETED)
        booking = _confirmed_booking_with_ticket(event, Decimal("75.00"))
        booking.status = Booking.Status.REFUND_FAILED
        booking.save(update_fields=["status"])

        sales = get_event_sales(event)

        assert sales["gross_revenue"] == Decimal("75.00")
        assert sales["tickets_sold"] == 1
        assert sales["tickets"][0]["status"] == "confirmed"

    def test_refund_failed_booking_recovers_to_confirmed_tag_after_retry_succeeds(self):
        event = EventFactory(status=Event.Status.COMPLETED)
        booking = _confirmed_booking_with_ticket(event, Decimal("30.00"))
        booking.status = Booking.Status.REFUND_FAILED
        booking.save(update_fields=["status"])
        assert get_event_sales(event)["tickets"][0]["status"] == "confirmed"

        booking.status = Booking.Status.REFUNDED
        booking.save(update_fields=["status"])

        sales = get_event_sales(event)
        assert sales["tickets"][0]["status"] == "refunded"
        assert sales["gross_revenue"] == Decimal("0.00")

    def test_independent_of_any_existing_payout_snapshot(self):
        event = EventFactory(status=Event.Status.COMPLETED)
        booking = _confirmed_booking_with_ticket(event, Decimal("100.00"))
        payout, _ = create_payout(event)

        assert payout.gross_revenue == Decimal("100.00")

        booking.status = Booking.Status.REFUNDED
        booking.save(update_fields=["status"])

        sales = get_event_sales(event)
        assert sales["gross_revenue"] == Decimal("0.00")
        assert sales["tickets_sold"] == 1
        assert sales["tickets"][0]["status"] == "refunded"

        payout.refresh_from_db()
        assert payout.gross_revenue == Decimal("100.00")


class TestCreatePayout:
    def test_creates_with_expected_fields(self):
        event = EventFactory(status=Event.Status.COMPLETED)
        _confirmed_booking_with_ticket(event, Decimal("100.00"))

        payout, created = create_payout(event)

        assert created is True
        assert payout.event_id == event.id
        assert payout.status == OrganizerPayout.Status.PENDING
        assert payout.payout_reference == f"PAYOUT-{event.id}"
        assert payout.period_start == event.start_datetime
        assert payout.period_end == event.end_datetime
        assert payout.gross_revenue == Decimal("100.00")
        assert payout.platform_fee == Decimal("10.00")
        assert payout.net_amount == Decimal("90.00")

    def test_pre_check_returns_existing_row_without_creating_a_second_one(self):
        event = EventFactory(status=Event.Status.COMPLETED)

        first, first_created = create_payout(event)
        second, second_created = create_payout(event)

        assert first_created is True
        assert second_created is False
        assert first.id == second.id
        assert OrganizerPayout.objects.filter(event=event).count() == 1

    def test_enqueues_ready_notification_only_on_actual_creation(
        self, monkeypatch, django_capture_on_commit_callbacks
    ):
        mock_task = MagicMock()
        monkeypatch.setattr(
            "apps.payouts.tasks.send_payout_ready_notification", mock_task
        )
        event = EventFactory(status=Event.Status.COMPLETED)

        with django_capture_on_commit_callbacks(execute=True):
            payout, created = create_payout(event)

        assert created is True
        mock_task.delay.assert_called_once_with(str(payout.id))

        mock_task.reset_mock()
        with django_capture_on_commit_callbacks(execute=True):
            create_payout(event)

        mock_task.delay.assert_not_called()

    @pytest.mark.django_db(transaction=True)
    def test_concurrent_calls_for_the_same_event_yield_exactly_one_payout(self):
        event = EventFactory(status=Event.Status.COMPLETED)

        results = []
        errors = []
        barrier = threading.Barrier(2)

        def attempt():
            barrier.wait()
            try:
                payout, created = create_payout(event)
                results.append((payout.id, created))
            except Exception as exc:
                errors.append(exc)
            finally:
                connection.close()

        threads = [threading.Thread(target=attempt) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
        assert OrganizerPayout.objects.filter(event=event).count() == 1
        payout_ids = {pid for pid, _ in results}
        assert len(payout_ids) == 1
        created_flags = sorted(created for _, created in results)
        assert created_flags == [False, True]


class TestCreatePayoutsForCompletedEvents:
    def test_creates_a_payout_per_completed_unpaid_event_only(self):
        completed_unpaid = EventFactory(status=Event.Status.COMPLETED)
        EventFactory(status=Event.Status.APPROVED)
        already_paid = EventFactory(status=Event.Status.COMPLETED)
        OrganizerPayoutFactory(event=already_paid)

        created_count = create_payouts_for_completed_events()

        assert created_count == 1
        assert OrganizerPayout.objects.filter(event=completed_unpaid).exists()
        assert OrganizerPayout.objects.filter(event=already_paid).count() == 1

    def test_running_twice_does_not_double_create(self):
        event = EventFactory(status=Event.Status.COMPLETED)

        first_run = create_payouts_for_completed_events()
        second_run = create_payouts_for_completed_events()

        assert first_run == 1
        assert second_run == 0
        assert OrganizerPayout.objects.filter(event=event).count() == 1

    def test_soft_deleted_completed_event_still_gets_a_payout(self):
        event = EventFactory(status=Event.Status.COMPLETED, is_active=False)

        created_count = create_payouts_for_completed_events()

        assert created_count == 1
        assert OrganizerPayout.objects.filter(event=event).exists()


class TestRequestPayoutSettlement:
    def test_flips_pending_to_processing_and_enqueues_settle_task(
        self, monkeypatch, django_capture_on_commit_callbacks
    ):
        mock_task = MagicMock()
        monkeypatch.setattr("apps.payouts.tasks.settle_payout", mock_task)
        payout = OrganizerPayoutFactory(status=OrganizerPayout.Status.PENDING)

        with django_capture_on_commit_callbacks(execute=True):
            result = request_payout_settlement(payout)

        assert result.status == OrganizerPayout.Status.PROCESSING
        payout.refresh_from_db()
        assert payout.status == OrganizerPayout.Status.PROCESSING
        mock_task.delay.assert_called_once_with(str(payout.id))

    def test_failed_can_be_re_settled(self):
        payout = OrganizerPayoutFactory(status=OrganizerPayout.Status.FAILED)

        result = request_payout_settlement(payout)

        assert result.status == OrganizerPayout.Status.PROCESSING

    @pytest.mark.parametrize(
        "status",
        [OrganizerPayout.Status.PROCESSING, OrganizerPayout.Status.SETTLED],
    )
    def test_raises_when_not_pending_or_failed(self, status):
        payout = OrganizerPayoutFactory(status=status)

        with pytest.raises(PayoutNotSettleableError):
            request_payout_settlement(payout)


class TestSettlePayout:
    def test_active_organizer_settles_and_stamps_settled_at(
        self, monkeypatch, django_capture_on_commit_callbacks
    ):
        mock_task = MagicMock()
        monkeypatch.setattr(
            "apps.payouts.tasks.send_payout_settled_notification", mock_task
        )
        payout = OrganizerPayoutFactory(status=OrganizerPayout.Status.PROCESSING)

        with django_capture_on_commit_callbacks(execute=True):
            settle_payout(payout.id)

        payout.refresh_from_db()
        assert payout.status == OrganizerPayout.Status.SETTLED
        assert payout.settled_at is not None
        mock_task.delay.assert_called_once_with(str(payout.id))

    def test_inactive_organizer_results_in_failed_not_an_unhandled_exception(
        self, monkeypatch, django_capture_on_commit_callbacks
    ):
        mock_task = MagicMock()
        monkeypatch.setattr(
            "apps.payouts.tasks.send_payout_settled_notification", mock_task
        )
        organizer = UserFactory(is_active=False)
        event = EventFactory(status=Event.Status.COMPLETED, organizer=organizer)
        payout = OrganizerPayoutFactory(
            event=event, status=OrganizerPayout.Status.PROCESSING
        )

        with django_capture_on_commit_callbacks(execute=True):
            settle_payout(payout.id)

        payout.refresh_from_db()
        assert payout.status == OrganizerPayout.Status.FAILED
        assert payout.settled_at is None
        mock_task.delay.assert_not_called()

    def test_reactivating_organizer_then_retrying_settle_succeeds(self):
        organizer = UserFactory(is_active=False)
        event = EventFactory(status=Event.Status.COMPLETED, organizer=organizer)
        payout = OrganizerPayoutFactory(
            event=event, status=OrganizerPayout.Status.PENDING
        )

        request_payout_settlement(payout)
        settle_payout(payout.id)
        payout.refresh_from_db()
        assert payout.status == OrganizerPayout.Status.FAILED

        organizer.is_active = True
        organizer.save(update_fields=["is_active"])

        request_payout_settlement(payout)
        settle_payout(payout.id)
        payout.refresh_from_db()
        assert payout.status == OrganizerPayout.Status.SETTLED

    def test_noop_if_row_is_no_longer_processing(self, monkeypatch):
        mock_task = MagicMock()
        monkeypatch.setattr(
            "apps.payouts.tasks.send_payout_settled_notification", mock_task
        )
        payout = OrganizerPayoutFactory(status=OrganizerPayout.Status.SETTLED)

        settle_payout(payout.id)

        payout.refresh_from_db()
        assert payout.status == OrganizerPayout.Status.SETTLED
        mock_task.delay.assert_not_called()

    def test_lock_is_scoped_to_the_payout_row_only(self, monkeypatch):
        organizer = UserFactory(is_active=True)
        event = EventFactory(status=Event.Status.COMPLETED, organizer=organizer)
        payout = OrganizerPayoutFactory(
            event=event, status=OrganizerPayout.Status.PROCESSING
        )

        real_filter = Event.all_objects.filter
        calls = []

        def spy_filter(*args, **kwargs):
            calls.append(kwargs)
            return real_filter(*args, **kwargs)

        monkeypatch.setattr(Event.all_objects, "filter", spy_filter)

        settle_payout(payout.id)

        assert any("organizer__is_active" in call for call in calls), (
            "organizer-active check should be its own unlocked Event query, "
            "not a select_related()/select_for_update() traversal from OrganizerPayout"
        )

    def test_soft_deleted_completed_event_with_active_organizer_still_settles(self):
        organizer = UserFactory(is_active=True)
        event = EventFactory(
            status=Event.Status.COMPLETED, organizer=organizer, is_active=False
        )
        payout = OrganizerPayoutFactory(
            event=event, status=OrganizerPayout.Status.PROCESSING
        )

        settle_payout(payout.id)

        payout.refresh_from_db()
        assert payout.status == OrganizerPayout.Status.SETTLED
