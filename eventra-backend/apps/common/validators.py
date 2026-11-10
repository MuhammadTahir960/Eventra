import contextlib
import unicodedata

from django.core.exceptions import ValidationError

from .constants import (
    ALLOWED_IMAGE_FORMATS,
    MAX_IMAGE_PIXELS,
    MAX_IMAGE_UPLOAD_SIZE_MB,
    NAME_PUNCTUATION,
    REPEATED_PUNCTUATION,
    TEXT_ERROR,
    TEXT_JOINERS,
    TITLE_PUNCTUATION,
)


def validate_image_upload_size(file) -> None:
    max_bytes = MAX_IMAGE_UPLOAD_SIZE_MB * 1024 * 1024
    if file.size > max_bytes:
        raise ValidationError(f"Image must be {MAX_IMAGE_UPLOAD_SIZE_MB}MB or smaller.")
    _check_pixel_count(file)


def _check_pixel_count(file) -> None:
    from PIL import Image

    try:
        with Image.open(file) as img:
            width, height = img.size
            image_format = img.format
    except Image.DecompressionBombError as exc:
        raise ValidationError("Image dimensions are too large.") from exc
    except Exception as exc:
        raise ValidationError("Upload a JPEG, PNG or WebP image.") from exc
    finally:
        with contextlib.suppress(Exception):
            file.seek(0)
    if width * height > MAX_IMAGE_PIXELS:
        raise ValidationError("Image dimensions are too large.")
    if image_format not in ALLOWED_IMAGE_FORMATS:
        raise ValidationError("Upload a JPEG, PNG or WebP image.")


def has_allowed_text(value: str, *, multiline: bool = False) -> bool:
    extra = TEXT_JOINERS + ("\n\r\t" if multiline else "")
    return all(
        char in extra
        or unicodedata.category(char)[0] in "LMNPS"
        or unicodedata.category(char) == "Zs"
        for char in value
    )


def validate_single_line_text(value: str) -> None:
    if not has_allowed_text(value):
        raise ValidationError(TEXT_ERROR)


def validate_multiline_text(value: str) -> None:
    if not has_allowed_text(value, multiline=True):
        raise ValidationError(TEXT_ERROR)


def validate_proper_name(value: str) -> None:
    allowed = NAME_PUNCTUATION + TEXT_JOINERS
    if not any(char.isalpha() for char in value) or not all(
        char in allowed or unicodedata.category(char)[0] in "LM" for char in value
    ):
        raise ValidationError(
            "Use letters, spaces, hyphens, apostrophes and full stops only."
        )


def validate_display_name(value: str) -> None:
    allowed = TITLE_PUNCTUATION + TEXT_JOINERS
    if (
        not any(char.isalnum() for char in value)
        or REPEATED_PUNCTUATION.search(value)
        or not all(
            char in allowed or unicodedata.category(char)[0] in "LMN" for char in value
        )
    ):
        raise ValidationError(
            "Use letters, numbers, spaces and basic punctuation only: "
            "& ' - : , . ! ? ( ) / + # %"
        )
