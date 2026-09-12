import logging
from decimal import ROUND_HALF_UP, Decimal

from django.db import IntegrityError, models, transaction
from django.utils import timezone

from apps.bookings.models import Booking
from apps.events.models import Event
from apps.tickets.models import Ticket

from .models import OrganizerPayout

PLATFORM_FEE_PERCENTAGE = Decimal("0.10")

logger = logging.getLogger(__name__)


class PayoutNotSettleableError(Exception):
    """Raised when settle is attempted on a payout that isn't pending or failed."""


class OrganizerInactiveError(Exception):
    """Raised inside settle_payout() when the event's organizer account is no longer active."""


def _sum_confirmed_booking_totals(event: Event) -> Decimal:
    total = (
        Booking.objects.filter(
            tickets__event_seat__event=event, status=Booking.Status.CONFIRMED
        )
        .distinct()
        .aggregate(total=models.Sum("total_amount"))["total"]
    )
    return total or Decimal("0.00")


def compute_payout_amounts(event: Event) -> tuple[Decimal, Decimal, Decimal]:
    gross_revenue = _sum_confirmed_booking_totals(event)
    platform_fee = (gross_revenue * PLATFORM_FEE_PERCENTAGE).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    net_amount = gross_revenue - platform_fee
    return gross_revenue, platform_fee, net_amount


_SOLD_BOOKING_STATUSES = (
    Booking.Status.CONFIRMED,
    Booking.Status.REFUNDED,
    Booking.Status.REFUND_FAILED,
)


def _ticket_sale_amount(ticket: Ticket) -> Decimal:
    seat = ticket.event_seat
    return (
        seat.price_override
        if seat.price_override is not None
        else seat.ticket_tier.price
    )


def get_event_sales(event: Event) -> dict:
    tickets = (
        Ticket.objects.filter(
            event_seat__event=event, booking__status__in=_SOLD_BOOKING_STATUSES
        )
        .select_related("booking", "event_seat", "event_seat__ticket_tier")
        .order_by("-created_at")
    )

    entries = []
    gross_revenue = Decimal("0.00")
    for ticket in tickets:
        amount = _ticket_sale_amount(ticket)
        is_refunded = ticket.booking.status == Booking.Status.REFUNDED
        if not is_refunded:
            gross_revenue += amount
        entries.append(
            {
                "ticket_id": ticket.id,
                "ticket_code": ticket.ticket_code,
                "amount": amount,
                "status": "refunded" if is_refunded else "confirmed",
            }
        )

    return {
        "tickets_sold": len(entries),
        "gross_revenue": gross_revenue,
        "tickets": entries,
    }


def create_payout(event: Event) -> tuple[OrganizerPayout, bool]:
    existing = OrganizerPayout.objects.filter(event=event).first()
    if existing is not None:
        return existing, False

    gross_revenue, platform_fee, net_amount = compute_payout_amounts(event)

    try:
        with transaction.atomic():
            payout = OrganizerPayout.objects.create(
                event=event,
                gross_revenue=gross_revenue,
                platform_fee=platform_fee,
                net_amount=net_amount,
                status=OrganizerPayout.Status.PENDING,
                payout_reference=f"PAYOUT-{event.id}",
                period_start=event.start_datetime,
                period_end=event.end_datetime,
            )
        created = True
    except IntegrityError:
        payout = OrganizerPayout.objects.get(event=event)
        created = False

    if created:
        transaction.on_commit(lambda: _enqueue_payout_ready_notification(payout.id))

    return payout, created


def create_payouts_for_completed_events() -> int:
    completed_event_ids = list(
        Event.all_objects.filter(
            status=Event.Status.COMPLETED, payout__isnull=True
        ).values_list("id", flat=True)
    )

    created_count = 0
    for event_id in completed_event_ids:
        event = Event.all_objects.get(id=event_id)
        _, created = create_payout(event)
        if created:
            created_count += 1

    return created_count


def request_payout_settlement(payout: OrganizerPayout) -> OrganizerPayout:
    with transaction.atomic():
        payout = OrganizerPayout.objects.select_for_update(of=("self",)).get(
            id=payout.id
        )

        if payout.status not in (
            OrganizerPayout.Status.PENDING,
            OrganizerPayout.Status.FAILED,
        ):
            raise PayoutNotSettleableError(
                f"Payout {payout.id} is '{payout.status}', not 'pending' or 'failed'."
            )

        payout.status = OrganizerPayout.Status.PROCESSING
        payout.save(update_fields=["status", "updated_at"])

        transaction.on_commit(lambda: _enqueue_settle_payout(payout.id))

    return payout


def settle_payout(payout_id) -> None:
    with transaction.atomic():
        payout = OrganizerPayout.objects.select_for_update(of=("self",)).get(
            id=payout_id
        )

        if payout.status != OrganizerPayout.Status.PROCESSING:
            return

        try:
            organizer_is_active = Event.all_objects.filter(
                id=payout.event_id, organizer__is_active=True
            ).exists()
            if not organizer_is_active:
                raise OrganizerInactiveError(
                    f"Organizer for event {payout.event_id} is not active."
                )
        except OrganizerInactiveError:
            logger.exception("Payout settlement failed for payout %s", payout.id)
            payout.status = OrganizerPayout.Status.FAILED
            payout.save(update_fields=["status", "updated_at"])
            return

        payout.status = OrganizerPayout.Status.SETTLED
        payout.settled_at = timezone.now()
        payout.save(update_fields=["status", "settled_at", "updated_at"])

        transaction.on_commit(lambda: _enqueue_payout_settled_notification(payout.id))


def _enqueue_payout_ready_notification(payout_id) -> None:
    from apps.payouts.tasks import send_payout_ready_notification

    send_payout_ready_notification.delay(str(payout_id))


def _enqueue_payout_settled_notification(payout_id) -> None:
    from apps.payouts.tasks import send_payout_settled_notification

    send_payout_settled_notification.delay(str(payout_id))


def _enqueue_settle_payout(payout_id) -> None:
    from apps.payouts.tasks import settle_payout

    settle_payout.delay(str(payout_id))
