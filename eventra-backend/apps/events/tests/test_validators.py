import pytest
from django.core.exceptions import ValidationError

from ..validators import validate_no_web_address


@pytest.mark.parametrize(
    "title",
    ["Gig at www.evil.example", "evil.example", "Visit example.org/login", "WWW.X.CO"],
)
def test_titles_with_web_addresses_are_rejected(title):
    with pytest.raises(ValidationError):
        validate_no_web_address(title)


@pytest.mark.parametrize(
    "title",
    [
        "St. Patrick's Day",
        "Vol. 2",
        "Jazz Night 2.0",
        "Rock & Roll: Live!",
        "e.g. talks",
    ],
)
def test_ordinary_titles_pass(title):
    validate_no_web_address(title)
