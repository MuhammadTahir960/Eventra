import pytest
from rest_framework.exceptions import Throttled

from ..exceptions import _retry_message, api_exception_handler


@pytest.mark.parametrize(
    ("wait", "text"),
    [
        (None, "try again later."),
        (12, "try again in a minute."),
        (61, "try again in 2 minutes."),
        (3584, "try again in 60 minutes."),
        (3601, "try again in 2 hours."),
    ],
)
def test_retry_message_is_plain_and_rounds_up(wait, text):
    assert _retry_message(wait) == f"Too many requests. Please {text}"


def test_handler_replaces_the_detail_and_keeps_retry_after():
    response = api_exception_handler(Throttled(wait=120), {})
    assert response.status_code == 429
    assert (
        response.data["detail"] == "Too many requests. Please try again in 2 minutes."
    )
    assert response["Retry-After"] == "120"
