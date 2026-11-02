from math import ceil

from rest_framework.exceptions import Throttled
from rest_framework.views import exception_handler


def _retry_message(wait: float | None) -> str:
    if wait is None:
        return "Too many requests. Please try again later."
    if wait <= 60:
        return "Too many requests. Please try again in a minute."
    if wait <= 3600:
        return f"Too many requests. Please try again in {ceil(wait / 60)} minutes."
    hours = ceil(wait / 3600)
    unit = "hour" if hours == 1 else "hours"
    return f"Too many requests. Please try again in {hours} {unit}."


def api_exception_handler(exc, context):
    if isinstance(exc, Throttled):
        exc.detail = _retry_message(exc.wait)
    return exception_handler(exc, context)
