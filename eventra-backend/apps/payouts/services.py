import logging
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.db import IntegrityError, models, transaction
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.bookings.models import Booking
from apps.events.models import Event
from apps.payments.constants import UNFINISHED_REFUND_STATUSES
from apps.payments.models import Refund, RefundItem
from apps.payments.services import refunded_so_far
from apps.tickets.models import Ticket

from .models import OrganizerPayout

PLATFORM_FEE_PERCENTAGE = Decimal("0.10")
PAYOUT_WAIT_HOURS = 24

logger = logging.getLogger(__name__)


class PayoutNotSettleableError(Exception):
    """Raised when settle is attempted on a payout that isn't pending or failed."""


class PayoutNotAvailableError(Exception):
    """Raised when an event is not completed, too early, sold nothing or is paid."""


class OrganizerInactiveError(Exception):
    """Raised inside settle_payout() when the event's organizer account is no longer active."""


def _partial_refunds(event) -> models.QuerySet:
    return RefundItem.objects.filter(
        ticket__event_seat__event=event,
        refund__booking__status=Booking.Status.CONFIRMED,
    )


def _sum_confirmed_booking_totals(event: Event) -> Decimal:
    total = Ticket.objects.filter(
        event_seat__event=event, booking__status=Booking.Status.CONFIRMED
    ).aggregate(total=models.Sum("price"))["total"]
    refunded = _partial_refunds(event).aggregate(total=models.Sum("amount"))["total"]
    return (total or Decimal("0.00")) - (refunded or Decimal("0.00"))


def compute_payout_amounts(event: Event) -> tuple[Decimal, Decimal, Decimal]:
    return split_gross_revenue(_sum_confirmed_booking_totals(event))


def split_gross_revenue(gross_revenue: Decimal) -> tuple[Decimal, Decimal, Decimal]:
    platform_fee = (gross_revenue * PLATFORM_FEE_PERCENTAGE).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    net_amount = gross_revenue - platform_fee
    return gross_revenue, platform_fee, net_amount


def get_event_sales(event: Event) -> dict:
    tickets = (
        Ticket.objects.filter(
            event_seat__event=event, booking__status__in=Booking.PAID_STATUSES
        )
        .select_related("booking")
        .annotate(refunded=refunded_so_far())
        .order_by("-created_at")
    )

    entries = []
    gross_revenue = Decimal("0.00")
    for ticket in tickets:
        amount = ticket.price - ticket.refunded
        is_refunded = ticket.booking.status == Booking.Status.REFUNDED
        if not is_refunded:
            gross_revenue += amount
        entries.append(
            {
                "ticket_id": ticket.id,
                "ticket_code": ticket.ticket_code,
                "amount": amount,
                "refunded": ticket.refunded,
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

    gross_revenue, platform_fee, _ = compute_payout_amounts(event)

    try:
        with transaction.atomic():
            payout = OrganizerPayout.objects.create(
                event=event,
                gross_revenue=gross_revenue,
                platform_fee=platform_fee,
                status=OrganizerPayout.Status.PENDING,
            )
        created = True
    except IntegrityError:
        payout = OrganizerPayout.objects.get(event=event)
        created = False

    return payout, created


def payout_available_at(event: Event):
    return event.completed_at + timedelta(hours=PAYOUT_WAIT_HOURS)


def awaiting_payout(events) -> models.QuerySet:
    sold = Booking.objects.filter(
        tickets__event_seat__event=models.OuterRef("pk"),
        status=Booking.Status.CONFIRMED,
    )
    gross = (
        Ticket.objects.filter(
            event_seat__event=models.OuterRef("pk"),
            booking__status=Booking.Status.CONFIRMED,
        )
        .order_by()
        .annotate(group=models.Value(1))
        .values("group")
        .annotate(total=models.Sum("price"))
        .values("total")
    )
    refunded = (
        _partial_refunds(models.OuterRef("pk"))
        .order_by()
        .annotate(group=models.Value(1))
        .values("group")
        .annotate(total=models.Sum("amount"))
        .values("total")
    )
    zero = models.Value(Decimal("0.00"))
    return (
        events.filter(status=Event.Status.COMPLETED, payout__isnull=True)
        .filter(models.Exists(sold))
        .annotate(
            gross_revenue=Coalesce(models.Subquery(gross), zero)
            - Coalesce(models.Subquery(refunded), zero)
        )
        .select_related("organizer", "venue")
        .order_by("completed_at", "id")
    )


def pay_out_event(event: Event) -> OrganizerPayout:
    with transaction.atomic():
        event = Event.all_objects.select_for_update(of=("self",)).get(pk=event.pk)
        if event.status != Event.Status.COMPLETED:
            raise PayoutNotAvailableError("Only a completed event can be paid out.")
        if OrganizerPayout.objects.filter(event=event).exists():
            raise PayoutNotAvailableError("This event has already been paid out.")
        if not awaiting_payout(Event.all_objects.filter(pk=event.pk)).exists():
            raise PayoutNotAvailableError(
                "No tickets were sold, so there is nothing to pay out."
            )
        if Refund.objects.filter(
            items__ticket__event_seat__event=event,
            status__in=UNFINISHED_REFUND_STATUSES,
        ).exists():
            raise PayoutNotAvailableError(
                "Refunds for this event are still being processed."
            )
        available_at = payout_available_at(event)
        if timezone.now() < available_at:
            raise PayoutNotAvailableError(
                f"Payout becomes available at {available_at:%Y-%m-%d %H:%M} UTC."
            )

        payout, _ = create_payout(event)
        payout.status = OrganizerPayout.Status.PROCESSING
        payout.save(update_fields=["status", "updated_at"])
        transaction.on_commit(lambda: _enqueue_settle_payout_or_fail(payout.id))

    return payout


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

        transaction.on_commit(lambda: _enqueue_settle_payout_or_fail(payout.id))

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

        transaction.on_commit(
            lambda: _enqueue_payout_settled_notification(payout.id), robust=True
        )


def _enqueue_payout_settled_notification(payout_id) -> None:
    from apps.payouts.tasks import send_payout_settled_notification

    send_payout_settled_notification.delay(str(payout_id))


def _enqueue_settle_payout(payout_id) -> None:
    from apps.payouts.tasks import settle_payout

    settle_payout.delay(str(payout_id))


def _enqueue_settle_payout_or_fail(payout_id) -> None:
    try:
        _enqueue_settle_payout(payout_id)
    except Exception:
        logger.exception(
            "Could not enqueue settlement for payout %s; marking it failed", payout_id
        )
        OrganizerPayout.objects.filter(
            id=payout_id, status=OrganizerPayout.Status.PROCESSING
        ).update(status=OrganizerPayout.Status.FAILED, updated_at=timezone.now())
