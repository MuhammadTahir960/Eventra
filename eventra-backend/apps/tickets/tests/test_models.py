import re

from ..models import TICKET_CODE_ALPHABET, _generate_ticket_code


def test_ticket_codes_are_grouped_and_easy_to_read():
    codes = {_generate_ticket_code() for _ in range(2000)}
    assert len(codes) == 2000
    for code in codes:
        assert re.fullmatch(r"[A-Z2-9]{4}-[A-Z2-9]{4}-[A-Z2-9]{4}", code)
        assert not set(code) & set("01OIL")
    assert set("".join(codes).replace("-", "")) == set(TICKET_CODE_ALPHABET)
