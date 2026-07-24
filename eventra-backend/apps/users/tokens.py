from django.core.signing import TimestampSigner, BadSignature, SignatureExpired

_signer = TimestampSigner(salt="users.email-verification")

TOKEN_MAX_AGE_SECONDS = 60 * 60 * 48


def generate_verification_token(user_id: int) -> str:
    return _signer.sign(str(user_id))


def verify_token(token: str) -> int | None:
    try:
        user_id = _signer.unsign(token, max_age=TOKEN_MAX_AGE_SECONDS)
        return int(user_id)
    except (BadSignature, SignatureExpired, ValueError):
        return None
