MAX_SEATS_PER_HOLD = 10
HOLD_DURATION_MINUTES = 5
MAX_ACTIVE_SEATS_PER_USER = 10

CLOSE_INVALID_TICKET = 4401  # missing / invalid / expired / already-used ticket
CLOSE_EVENT_NOT_VISIBLE = 4404  # event doesn't exist, or isn't visible to this user
CLOSE_UNEXPECTED_MESSAGE = 4400  # client sent something on this read-only socket
CLOSE_RATE_LIMITED = 4429  # too many connection attempts (mirrors HTTP 429)
