from celery import shared_task

from apps.notifications.services import (
    send_payout_ready_email,
    send_payout_settled_email,
)

from .models import OrganizerPayout
from .services import (
    create_payouts_for_completed_events as _create_payouts_for_completed_events,
)
from .services import settle_payout as _settle_payout


@shared_task(name="apps.payouts.tasks.create_payouts_for_completed_events")
def create_payouts_for_completed_events() -> int:
    return _create_payouts_for_completed_events()


@shared_task(name="apps.payouts.tasks.settle_payout")
def settle_payout(payout_id) -> None:
    _settle_payout(payout_id)


@shared_task(
    name="apps.payouts.tasks.send_payout_ready_notification",
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=3,
)
def send_payout_ready_notification(payout_id) -> None:
    payout = OrganizerPayout.objects.select_related("event__organizer").get(
        id=payout_id
    )
    send_payout_ready_email(payout)


@shared_task(
    name="apps.payouts.tasks.send_payout_settled_notification",
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=3,
)
def send_payout_settled_notification(payout_id) -> None:
    payout = OrganizerPayout.objects.select_related("event__organizer").get(
        id=payout_id
    )
    send_payout_settled_email(payout)
