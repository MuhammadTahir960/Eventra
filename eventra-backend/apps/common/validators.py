import contextlib

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


def _check_pixel_count(file) -> None:
    from PIL import Image

    try:
        with Image.open(file) as img:
            width, height = img.size
    except Image.DecompressionBombError as exc:
        raise ValidationError("Image dimensions are too large.") from exc
    except Exception:
        return
    finally:
        with contextlib.suppress(Exception):
            file.seek(0)
    if width * height > MAX_IMAGE_PIXELS:
        raise ValidationError("Image dimensions are too large.")
