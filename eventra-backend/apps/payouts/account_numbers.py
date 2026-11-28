import base64
import secrets

from cryptography.hazmat.primitives.ciphers.aead import AESSIV
from django.conf import settings
from django.core import signing
from django.core.exceptions import ImproperlyConfigured

NUMBER_LENGTH = 16
SIGNING_NAMESPACE = "payouts.account-number"
MAX_AGE_SECONDS = 60 * 60


def _cipher() -> AESSIV:
    try:
        return AESSIV(base64.urlsafe_b64decode(settings.PAYOUT_ACCOUNT_KEY))
    except ValueError as exc:
        raise ImproperlyConfigured(
            "PAYOUT_ACCOUNT_KEY must be 64 random bytes in URL-safe base64."
        ) from exc


def encrypt(number: str) -> bytes:
    return _cipher().encrypt(number.encode(), None)


def decrypt(ciphertext: bytes) -> str:
    return _cipher().decrypt(bytes(ciphertext), None).decode()


def masked(ciphertext: bytes) -> str:
    return f"•••• {decrypt(ciphertext)[-4:]}"


def issue() -> dict:
    number = "".join(secrets.choice("0123456789") for _ in range(NUMBER_LENGTH))
    return {"number": number, "token": signing.dumps(number, salt=SIGNING_NAMESPACE)}


def redeem(token: str) -> str:
    return signing.loads(token, salt=SIGNING_NAMESPACE, max_age=MAX_AGE_SECONDS)
