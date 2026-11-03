import re

from django.core.validators import FileExtensionValidator
from django.db import models


class Roles(models.TextChoices):
    ATTENDEE = "attendee", "Attendee"
    ORGANIZER = "organizer", "Organizer"
    ADMIN = "admin", "Admin"


IMAGE_EXTENSION_VALIDATOR = FileExtensionValidator(["jpg", "jpeg", "png", "webp"])

MAX_IMAGE_UPLOAD_SIZE_MB = 5

MAX_IMAGE_PIXELS = 25_000_000

ALLOWED_IMAGE_FORMATS = {"JPEG", "PNG", "WEBP"}

TEXT_JOINERS = "\u200c\u200d"

TEXT_ERROR = "This contains characters that aren't allowed."

NAME_PUNCTUATION = " '\u2019-."

TITLE_PUNCTUATION = " &'\u2019-\u2013:,.!?()/+#%"

REPEATED_PUNCTUATION = re.compile(r"([^\w\s])\1")
