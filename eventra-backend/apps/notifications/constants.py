from apps.payments.models import Refund

REFUND_REASONS = {
    Refund.Reason.CANCELLED_EVENT: "the event was cancelled",
    Refund.Reason.UNAVAILABLE: "we couldn't complete it: the reservation expired "
    "or the event is no longer available",
    Refund.Reason.POSTPONED: "you asked for a refund after the event was postponed",
    Refund.Reason.ABANDONED_EVENT: "the event couldn't be completed as planned",
    Refund.Reason.PRICE_DROP: "the organizer lowered the ticket price",
}

REMINDER_WINDOW_HOURS = 24

REMINDER_CLAIM_STALE_MINUTES = 15

REMINDER_MAX_ATTEMPTS = 3
