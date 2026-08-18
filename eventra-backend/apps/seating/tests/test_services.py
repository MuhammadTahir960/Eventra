import threading
import uuid
from datetime import timedelta

import pytest
from django.db import connection
from django.utils import timezone

from apps.events.factories import (
    EventFactory,
    TicketTierFactory,
    TierSectionMappingFactory,
)
from apps.events.models import Event
from apps.users.factories import UserFactory
from apps.venues.factories import SeatFactory, VenueFactory

from ..models import EventSeat, SeatHold
from ..services import (
    MAX_SEATS_PER_HOLD,
    AlreadyInstantiatedError,
    EmptySeatSelectionError,
    EventNotHoldableError,
    NotSeatedEventError,
    SeatLockConflictError,
    SeatsNotFoundError,
    SeatsUnavailableError,
    TooManySeatsError,
    UncoveredSectionsError,
    hold_seats,
    instantiate_event_seats,
)

pytestmark = pytest.mark.django_db


# ==================================================
# instantiate_event_seats
# ==================================================


def _seated_event_with_mapped_venue(*, section="Main"):
    venue = VenueFactory()
    SeatFactory(venue=venue, section=section, row_label="A", seat_number=1)
    SeatFactory(venue=venue, section=section, row_label="A", seat_number=2)
    event = EventFactory(venue=venue, is_seated=True, status=Event.Status.APPROVED)
    tier = TicketTierFactory(event=event)
    TierSectionMappingFactory(event=event, ticket_tier=tier, section=section)
    return event


def test_instantiate_creates_one_event_seat_per_venue_seat():
    event = _seated_event_with_mapped_venue()
    created = instantiate_event_seats(event)
    assert len(created) == 2
    assert EventSeat.objects.filter(event=event).count() == 2
    assert all(es.status == EventSeat.Status.AVAILABLE for es in created)


def test_instantiate_maps_tier_by_section():
    event = _seated_event_with_mapped_venue(section="VIP")
    tier = event.ticket_tiers.get()
    created = instantiate_event_seats(event)
    assert all(es.ticket_tier_id == tier.id for es in created)


def test_instantiate_rejects_non_seated_event():
    event = EventFactory(is_seated=False)
    with pytest.raises(NotSeatedEventError):
        instantiate_event_seats(event)


def test_instantiate_rejects_event_with_no_venue():
    event = EventFactory(venue=None, is_seated=True)
    with pytest.raises(NotSeatedEventError):
        instantiate_event_seats(event)


def test_instantiate_rejects_second_call():
    event = _seated_event_with_mapped_venue()
    instantiate_event_seats(event)
    with pytest.raises(AlreadyInstantiatedError):
        instantiate_event_seats(event)


def test_instantiate_reports_uncovered_sections_by_name():
    venue = VenueFactory()
    SeatFactory(venue=venue, section="Main", row_label="A", seat_number=1)
    SeatFactory(venue=venue, section="Balcony", row_label="A", seat_number=1)
    event = EventFactory(venue=venue, is_seated=True)
    tier = TicketTierFactory(event=event)
    TierSectionMappingFactory(event=event, ticket_tier=tier, section="Main")

    with pytest.raises(UncoveredSectionsError) as exc_info:
        instantiate_event_seats(event)
    assert exc_info.value.sections == ["Balcony"]


@pytest.mark.django_db(transaction=True)
def test_concurrent_instantiate_calls_exactly_one_wins():
    event = _seated_event_with_mapped_venue()

    outcomes = {}
    barrier = threading.Barrier(2)

    def attempt(key):
        barrier.wait()
        try:
            instantiate_event_seats(event)
            outcomes[key] = "success"
        except AlreadyInstantiatedError:
            outcomes[key] = "conflict"
        finally:
            connection.close()

    t1 = threading.Thread(target=attempt, args=("a",))
    t2 = threading.Thread(target=attempt, args=("b",))
    t1.start()
    t2.start()
    t1.join(timeout=10)
    t2.join(timeout=10)

    assert not t1.is_alive() and not t2.is_alive()
    values = list(outcomes.values())
    assert values.count("success") == 1
    assert values.count("conflict") == 1
    assert EventSeat.objects.filter(event=event).count() == 2


# ==================================================
# hold_seats — validation guards
# ==================================================


def test_hold_seats_rejects_empty_selection():
    event = _seated_event_with_mapped_venue()
    with pytest.raises(EmptySeatSelectionError):
        hold_seats(event=event, seat_ids=[], user=UserFactory(role="attendee"))


def test_hold_seats_rejects_over_the_cap():
    event = _seated_event_with_mapped_venue()
    too_many = [uuid.uuid4() for _ in range(MAX_SEATS_PER_HOLD + 1)]
    with pytest.raises(TooManySeatsError):
        hold_seats(event=event, seat_ids=too_many, user=UserFactory(role="attendee"))


def test_hold_seats_rejects_non_seated_event():
    event = EventFactory(is_seated=False, status=Event.Status.APPROVED)
    with pytest.raises(NotSeatedEventError):
        hold_seats(
            event=event, seat_ids=[uuid.uuid4()], user=UserFactory(role="attendee")
        )


@pytest.mark.parametrize(
    "status",
    [
        Event.Status.PENDING_APPROVAL,
        Event.Status.REJECTED,
        Event.Status.CANCELLED,
        Event.Status.COMPLETED,
    ],
)
def test_hold_seats_rejects_non_approved_event(status):
    event = EventFactory(is_seated=True, status=status)
    with pytest.raises(EventNotHoldableError):
        hold_seats(
            event=event, seat_ids=[uuid.uuid4()], user=UserFactory(role="attendee")
        )


def test_hold_seats_reports_unknown_seat_ids():
    event = _seated_event_with_mapped_venue()
    bogus_id = uuid.uuid4()
    with pytest.raises(SeatsNotFoundError) as exc_info:
        hold_seats(event=event, seat_ids=[bogus_id], user=UserFactory(role="attendee"))
    assert exc_info.value.seat_ids == [bogus_id]


def test_hold_seats_rejects_seat_belonging_to_a_different_event():
    event = _seated_event_with_mapped_venue()
    other_event = _seated_event_with_mapped_venue()
    instantiate_event_seats(other_event)
    other_seat = EventSeat.objects.filter(event=other_event).first()

    with pytest.raises(SeatsNotFoundError):
        hold_seats(
            event=event, seat_ids=[other_seat.id], user=UserFactory(role="attendee")
        )


# ==================================================
# hold_seats — success path
# ==================================================


def test_hold_seats_marks_seats_held_and_returns_shared_group_id():
    event = _seated_event_with_mapped_venue()
    instantiate_event_seats(event)
    seats = list(EventSeat.objects.filter(event=event))
    user = UserFactory(role="attendee")

    group_id, expires_at, held = hold_seats(
        event=event, seat_ids=[s.id for s in seats], user=user
    )

    assert len(held) == 2
    assert all(s.status == EventSeat.Status.HELD for s in held)
    db_seats = EventSeat.objects.filter(event=event)
    assert all(s.status == EventSeat.Status.HELD for s in db_seats)

    holds = SeatHold.objects.filter(event_seat__event=event)
    assert holds.count() == 2
    assert {h.group_id for h in holds} == {group_id}
    assert all(h.user_id == user.id for h in holds)
    assert all(h.expires_at == expires_at for h in holds)


def test_hold_seats_rejects_seat_held_by_a_different_user():
    event = _seated_event_with_mapped_venue()
    instantiate_event_seats(event)
    seat = EventSeat.objects.filter(event=event).first()
    other_user = UserFactory(role="attendee")
    hold_seats(event=event, seat_ids=[seat.id], user=other_user)

    with pytest.raises(SeatsUnavailableError) as exc_info:
        hold_seats(event=event, seat_ids=[seat.id], user=UserFactory(role="attendee"))
    assert exc_info.value.seat_ids == [seat.id]


def test_hold_seats_re_hold_by_same_user_refreshes_instead_of_conflicting():
    event = _seated_event_with_mapped_venue()
    instantiate_event_seats(event)
    seat = EventSeat.objects.filter(event=event).first()
    user = UserFactory(role="attendee")

    first_group_id, first_expiry, _ = hold_seats(
        event=event, seat_ids=[seat.id], user=user
    )
    SeatHold.objects.filter(event_seat=seat).update(
        expires_at=timezone.now() - timedelta(minutes=1)
    )

    second_group_id, second_expiry, held = hold_seats(
        event=event, seat_ids=[seat.id], user=user
    )

    assert second_group_id != first_group_id
    assert second_expiry > timezone.now()
    assert SeatHold.objects.filter(event_seat=seat).count() == 1
    assert SeatHold.objects.get(event_seat=seat).group_id == second_group_id
    seat.refresh_from_db()
    assert seat.status == EventSeat.Status.HELD


def test_hold_seats_rejects_booked_seat():
    event = _seated_event_with_mapped_venue()
    instantiate_event_seats(event)
    seat = EventSeat.objects.filter(event=event).first()
    seat.status = EventSeat.Status.BOOKED
    seat.save(update_fields=["status"])

    with pytest.raises(SeatsUnavailableError) as exc_info:
        hold_seats(event=event, seat_ids=[seat.id], user=UserFactory(role="attendee"))
    assert exc_info.value.seat_ids == [seat.id]


def test_hold_seats_reclaims_seat_whose_hold_has_expired_but_not_yet_been_swept():
    event = _seated_event_with_mapped_venue()
    instantiate_event_seats(event)
    seat = EventSeat.objects.filter(event=event).first()
    original_holder = UserFactory(role="attendee")
    new_user = UserFactory(role="attendee")

    original_group_id, _, _ = hold_seats(
        event=event, seat_ids=[seat.id], user=original_holder
    )
    SeatHold.objects.filter(event_seat=seat).update(
        expires_at=timezone.now() - timedelta(seconds=1)
    )
    seat.refresh_from_db()
    assert seat.status == EventSeat.Status.HELD

    new_group_id, new_expires_at, held = hold_seats(
        event=event, seat_ids=[seat.id], user=new_user
    )

    assert new_group_id != original_group_id
    assert new_expires_at > timezone.now()
    assert len(held) == 1
    seat.refresh_from_db()
    assert seat.status == EventSeat.Status.HELD

    hold = SeatHold.objects.get(event_seat=seat)
    assert hold.user_id == new_user.id
    assert hold.group_id == new_group_id
    assert hold.expires_at == new_expires_at


def test_hold_seats_reclaims_all_seats_in_a_multi_seat_request_when_every_hold_has_expired():
    event = _seated_event_with_mapped_venue()
    instantiate_event_seats(event)
    seats = list(EventSeat.objects.filter(event=event))
    assert len(seats) == 2
    original_holder = UserFactory(role="attendee")
    new_user = UserFactory(role="attendee")

    hold_seats(event=event, seat_ids=[s.id for s in seats], user=original_holder)
    SeatHold.objects.filter(event_seat__in=seats).update(
        expires_at=timezone.now() - timedelta(seconds=1)
    )

    group_id, expires_at, held = hold_seats(
        event=event, seat_ids=[s.id for s in seats], user=new_user
    )

    assert len(held) == 2
    holds = SeatHold.objects.filter(event_seat__in=seats)
    assert holds.count() == 2
    assert {h.group_id for h in holds} == {group_id}
    assert all(h.user_id == new_user.id for h in holds)


def test_hold_seats_mixed_batch_one_reclaimable_one_still_live_conflicts_atomically():
    event = _seated_event_with_mapped_venue()
    instantiate_event_seats(event)
    reclaimable_seat, still_live_seat = list(EventSeat.objects.filter(event=event))
    other_user_a = UserFactory(role="attendee")
    other_user_b = UserFactory(role="attendee")

    hold_seats(event=event, seat_ids=[reclaimable_seat.id], user=other_user_a)
    SeatHold.objects.filter(event_seat=reclaimable_seat).update(
        expires_at=timezone.now() - timedelta(seconds=1)
    )
    hold_seats(event=event, seat_ids=[still_live_seat.id], user=other_user_b)

    with pytest.raises(SeatsUnavailableError) as exc_info:
        hold_seats(
            event=event,
            seat_ids=[reclaimable_seat.id, still_live_seat.id],
            user=UserFactory(role="attendee"),
        )
    assert exc_info.value.seat_ids == [still_live_seat.id]

    assert SeatHold.objects.filter(event_seat=reclaimable_seat).count() == 1
    assert SeatHold.objects.get(event_seat=reclaimable_seat).user_id == other_user_a.id


def test_hold_seats_still_conflicts_on_a_hold_that_has_not_expired_yet():
    event = _seated_event_with_mapped_venue()
    instantiate_event_seats(event)
    seat = EventSeat.objects.filter(event=event).first()
    original_holder = UserFactory(role="attendee")
    hold_seats(event=event, seat_ids=[seat.id], user=original_holder)

    with pytest.raises(SeatsUnavailableError) as exc_info:
        hold_seats(event=event, seat_ids=[seat.id], user=UserFactory(role="attendee"))
    assert exc_info.value.seat_ids == [seat.id]


def test_hold_seats_dedupes_repeated_seat_ids():
    event = _seated_event_with_mapped_venue()
    instantiate_event_seats(event)
    seat = EventSeat.objects.filter(event=event).first()
    user = UserFactory(role="attendee")

    group_id, expires_at, held = hold_seats(
        event=event, seat_ids=[seat.id, seat.id], user=user
    )
    assert len(held) == 1
    assert SeatHold.objects.filter(event_seat=seat).count() == 1


# ==================================================
# hold_seats — concurrency (the highest-risk path)
# ==================================================


@pytest.mark.django_db(transaction=True)
def test_concurrent_holds_on_the_same_seat_exactly_one_wins():
    venue = VenueFactory()
    SeatFactory(venue=venue, section="Main", row_label="A", seat_number=1)
    event = EventFactory(venue=venue, is_seated=True, status=Event.Status.APPROVED)
    tier = TicketTierFactory(event=event)
    TierSectionMappingFactory(event=event, ticket_tier=tier, section="Main")
    instantiate_event_seats(event)
    event_seat = EventSeat.objects.get(event=event)

    user_a = UserFactory(role="attendee")
    user_b = UserFactory(role="attendee")

    outcomes = {}
    barrier = threading.Barrier(2)

    def attempt(user, key):
        barrier.wait()
        try:
            hold_seats(event=event, seat_ids=[event_seat.id], user=user)
            outcomes[key] = "success"
        except SeatsUnavailableError:
            outcomes[key] = "conflict"
        except SeatLockConflictError:
            outcomes[key] = "lock_conflict"
        finally:
            connection.close()

    t1 = threading.Thread(target=attempt, args=(user_a, "a"))
    t2 = threading.Thread(target=attempt, args=(user_b, "b"))
    t1.start()
    t2.start()
    t1.join(timeout=10)
    t2.join(timeout=10)

    assert (
        not t1.is_alive() and not t2.is_alive()
    ), "a thread hung — NOWAIT should never block"
    values = list(outcomes.values())
    assert values.count("success") == 1
    assert values.count("conflict") + values.count("lock_conflict") == 1

    event_seat.refresh_from_db()
    assert event_seat.status == EventSeat.Status.HELD
    assert SeatHold.objects.filter(event_seat=event_seat).count() == 1


@pytest.mark.django_db(transaction=True)
def test_concurrent_reclaims_of_the_same_expired_unswept_hold_exactly_one_wins():
    venue = VenueFactory()
    SeatFactory(venue=venue, section="Main", row_label="A", seat_number=1)
    event = EventFactory(venue=venue, is_seated=True, status=Event.Status.APPROVED)
    tier = TicketTierFactory(event=event)
    TierSectionMappingFactory(event=event, ticket_tier=tier, section="Main")
    instantiate_event_seats(event)
    event_seat = EventSeat.objects.get(event=event)

    original_holder = UserFactory(role="attendee")
    hold_seats(event=event, seat_ids=[event_seat.id], user=original_holder)
    SeatHold.objects.filter(event_seat=event_seat).update(
        expires_at=timezone.now() - timedelta(seconds=1)
    )

    user_a = UserFactory(role="attendee")
    user_b = UserFactory(role="attendee")

    outcomes = {}
    barrier = threading.Barrier(2)

    def attempt(user, key):
        barrier.wait()
        try:
            hold_seats(event=event, seat_ids=[event_seat.id], user=user)
            outcomes[key] = "success"
        except SeatsUnavailableError:
            outcomes[key] = "conflict"
        except SeatLockConflictError:
            outcomes[key] = "lock_conflict"
        finally:
            connection.close()

    t1 = threading.Thread(target=attempt, args=(user_a, "a"))
    t2 = threading.Thread(target=attempt, args=(user_b, "b"))
    t1.start()
    t2.start()
    t1.join(timeout=10)
    t2.join(timeout=10)

    assert (
        not t1.is_alive() and not t2.is_alive()
    ), "a thread hung — NOWAIT should never block"
    values = list(outcomes.values())
    assert values.count("success") == 1
    assert values.count("conflict") + values.count("lock_conflict") == 1

    event_seat.refresh_from_db()
    assert event_seat.status == EventSeat.Status.HELD
    assert SeatHold.objects.filter(event_seat=event_seat).count() == 1
    winning_hold = SeatHold.objects.get(event_seat=event_seat)
    assert winning_hold.user_id in {user_a.id, user_b.id}
    assert winning_hold.user_id != original_holder.id
