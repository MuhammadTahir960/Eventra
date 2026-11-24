import re

from django.core.exceptions import ValidationError

WEB_ADDRESS = re.compile(r"\bwww\.|[^\W_]\.[^\W\d_]{2,}\b", re.IGNORECASE)


def validate_no_web_address(value: str) -> None:
    if WEB_ADDRESS.search(value):
        raise ValidationError(
            "Leave web addresses out of the title, such as www.example.com."
        )
