from apps.payments.models import Refund

REFUND_LINES = {
    Refund.Reason.CANCELLED_EVENT: "the event was cancelled, so we've refunded your "
    "booking in full. Your tickets are cancelled.",
    Refund.Reason.POSTPONED: "plans change, we get it. You asked for a refund after "
    "the date moved, so we've refunded your booking in full. Your tickets are "
    "cancelled.",
    Refund.Reason.UNAVAILABLE: "we couldn't complete your booking: the reservation "
    "ran out or the event is no longer on sale. We've refunded your payment in full.",
    Refund.Reason.PRICE_DROP: "good news: the organizer lowered the ticket price, so "
    "we've refunded the difference. Your tickets still work.",
    Refund.Reason.ABANDONED_EVENT: "the event couldn't go ahead as planned, so we've "
    "refunded part of your booking. Your tickets still work.",
}

REMINDER_WINDOW_HOURS = 24

REMINDER_CLAIM_STALE_MINUTES = 15

REMINDER_MAX_ATTEMPTS = 3

EMAIL_TAGLINE = "See it listed. Know someone checked."

EMAIL_REVIEW_LINE = (
    "Every listing is checked by a person before it goes on sale. "
    "That lowers the risk; it doesn't remove it."
)

REASON_SIGN_UP = "this address was used to sign up for Eventra"
REASON_RESET = "a password reset was requested for this address"
REASON_SIGN_UP_ATTEMPT = "someone tried to sign up with this address"
REASON_ACCOUNT_DELETED = "your Eventra account was deleted"
REASON_BOOKED = "you booked on Eventra"
REASON_ORGANIZER = "you organize events on Eventra"
