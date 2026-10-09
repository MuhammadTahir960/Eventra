import uuid

from django.core.signing import BadSignature, SignatureExpired, TimestampSigner
from django.utils.crypto import salted_hmac

_signer = TimestampSigner(salt="users.email-verification")

TOKEN_MAX_AGE_SECONDS = 60 * 60 * 48


def generate_verification_token(user_id: uuid.UUID | str) -> str:
    return _signer.sign(str(user_id))


def verify_token(token: str) -> str | None:
    try:
        raw_value = _signer.unsign(token, max_age=TOKEN_MAX_AGE_SECONDS)
        return str(uuid.UUID(raw_value))
    except (BadSignature, SignatureExpired, ValueError):
        return None


_password_reset_signer = TimestampSigner(salt="users.password-reset")

PASSWORD_RESET_MAX_AGE_SECONDS = 60 * 60


def password_fingerprint(user) -> str:
    return salted_hmac(
        "users.password-reset.fingerprint", user.password, algorithm="sha256"
    ).hexdigest()


def generate_password_reset_token(user) -> str:
    payload = f"{user.id}:{password_fingerprint(user)}"
    return _password_reset_signer.sign(payload)


def verify_password_reset_token(token: str) -> tuple[str, str] | None:
    try:
        raw_value = _password_reset_signer.unsign(
            token, max_age=PASSWORD_RESET_MAX_AGE_SECONDS
        )
    except (BadSignature, SignatureExpired):
        return None

    user_id, _, fingerprint = raw_value.rpartition(":")
    if not user_id or not fingerprint:
        return None
    try:
        uuid.UUID(user_id)
    except ValueError:
        return None
    return user_id, fingerprint
