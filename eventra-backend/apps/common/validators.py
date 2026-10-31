import contextlib
import re
import unicodedata

from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator

IMAGE_EXTENSION_VALIDATOR = FileExtensionValidator(["jpg", "jpeg", "png", "webp"])

MAX_IMAGE_UPLOAD_SIZE_MB = 5


def validate_image_upload_size(file) -> None:
    max_bytes = MAX_IMAGE_UPLOAD_SIZE_MB * 1024 * 1024
    if file.size > max_bytes:
        raise ValidationError(f"Image must be {MAX_IMAGE_UPLOAD_SIZE_MB}MB or smaller.")
    _check_pixel_count(file)


MAX_IMAGE_PIXELS = 25_000_000
ALLOWED_IMAGE_FORMATS = {"JPEG", "PNG", "WEBP"}


def _check_pixel_count(file) -> None:
    from PIL import Image

    try:
        with Image.open(file) as img:
            width, height = img.size
            image_format = img.format
    except Image.DecompressionBombError as exc:
        raise ValidationError("Image dimensions are too large.") from exc
    except Exception:
        return
    finally:
        with contextlib.suppress(Exception):
            file.seek(0)
    if width * height > MAX_IMAGE_PIXELS:
        raise ValidationError("Image dimensions are too large.")
    if image_format not in ALLOWED_IMAGE_FORMATS:
        raise ValidationError("Upload a JPEG, PNG or WebP image.")


_JOINERS = "\u200c\u200d"
_TEXT_ERROR = "This contains characters that aren't allowed."
_NAME_PUNCTUATION = " '\u2019-."


def has_allowed_text(value: str, *, multiline: bool = False) -> bool:
    extra = _JOINERS + ("\n\r\t" if multiline else "")
    return all(
        char in extra
        or unicodedata.category(char)[0] in "LMNPS"
        or unicodedata.category(char) == "Zs"
        for char in value
    )


def validate_single_line_text(value: str) -> None:
    if not has_allowed_text(value):
        raise ValidationError(_TEXT_ERROR)


def validate_multiline_text(value: str) -> None:
    if not has_allowed_text(value, multiline=True):
        raise ValidationError(_TEXT_ERROR)


def validate_person_name(value: str) -> None:
    allowed = _NAME_PUNCTUATION + _JOINERS
    if not any(char.isalpha() for char in value) or not all(
        char in allowed or unicodedata.category(char)[0] in "LM" for char in value
    ):
        raise ValidationError(
            "Use letters, spaces, hyphens, apostrophes and full stops only."
        )


_TITLE_PUNCTUATION = " &'\u2019-\u2013:,.!?()/+#%"
_REPEATED_PUNCTUATION = re.compile(r"([^\w\s])\1")


def validate_event_title(value: str) -> None:
    allowed = _TITLE_PUNCTUATION + _JOINERS
    if (
        not any(char.isalnum() for char in value)
        or _REPEATED_PUNCTUATION.search(value)
        or not all(
            char in allowed or unicodedata.category(char)[0] in "LMN" for char in value
        )
    ):
        raise ValidationError(
            "Use letters, numbers, spaces and basic punctuation only: "
            "& ' - : , . ! ? ( ) / + # %"
        )
