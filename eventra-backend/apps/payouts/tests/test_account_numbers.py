import pytest
from django.core import signing

from .. import account_numbers


def test_issued_numbers_are_16_digits_with_a_token_for_that_number():
    issued = account_numbers.issue()

    assert issued["number"].isdigit() and len(issued["number"]) == 16
    assert account_numbers.redeem(issued["token"]) == issued["number"]


def test_encryption_is_deterministic_and_reversible():
    first = account_numbers.encrypt("1234567812345678")

    assert first == account_numbers.encrypt("1234567812345678")
    assert b"1234567812345678" not in first
    assert account_numbers.decrypt(first) == "1234567812345678"
    assert account_numbers.masked(first) == "•••• 5678"


@pytest.mark.parametrize("token", ["", "1234567812345678", "not-a-token"])
def test_tokens_eventra_did_not_issue_are_refused(token):
    with pytest.raises(signing.BadSignature):
        account_numbers.redeem(token)


def test_altered_or_foreign_tokens_are_refused():
    token = account_numbers.issue()["token"]
    altered = token[:-1] + ("A" if token[-1] != "A" else "B")
    signed_elsewhere = signing.dumps("0000000000000000", salt="another-purpose")

    for bad in (altered, signed_elsewhere):
        with pytest.raises(signing.BadSignature):
            account_numbers.redeem(bad)
