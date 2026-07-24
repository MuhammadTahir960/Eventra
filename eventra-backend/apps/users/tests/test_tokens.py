from unittest.mock import patch
from apps.users import tokens as tokens_module
from apps.users.tokens import generate_verification_token, verify_token


def test_round_trip():
    token = generate_verification_token(42)
    assert verify_token(token) == 42


def test_tampered_token_rejected():
    token = generate_verification_token(42)
    tampered = token[:-1] + ("a" if token[-1] != "a" else "b")
    assert verify_token(tampered) is None


def test_garbage_token_rejected():
    assert verify_token("not-a-real-token") is None
    assert verify_token("") is None


def test_expired_token_rejected():
    token = generate_verification_token(42)

    future = __import__("time").time() + (60 * 60 * 48) + 60
    with patch("django.core.signing.time.time", return_value=future):
        assert verify_token(token) is None


def test_token_still_valid_just_under_the_expiry_boundary():
    token = generate_verification_token(42)

    almost_expired = __import__("time").time() + (60 * 60 * 48) - 60
    with patch("django.core.signing.time.time", return_value=almost_expired):
        assert verify_token(token) == 42


def test_valid_signature_with_non_numeric_payload_returns_none():
    with patch.object(tokens_module._signer, "unsign", return_value="not-an-int"):
        assert verify_token("irrelevant-since-unsign-is-mocked") is None
