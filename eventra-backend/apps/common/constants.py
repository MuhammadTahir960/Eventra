import re
from decimal import Decimal

from django.core.validators import FileExtensionValidator
from django.db import models


class Roles(models.TextChoices):
    ATTENDEE = "attendee", "Attendee"
    ORGANIZER = "organizer", "Organizer"
    ADMIN = "admin", "Admin"


IMAGE_EXTENSION_VALIDATOR = FileExtensionValidator(["jpg", "jpeg", "png", "webp"])

CURRENCY_PRICE_LIMITS = {
    "aed": (Decimal("4"), Decimal("40000")),
    "ars": (Decimal("2000"), Decimal("20000000")),
    "aud": (Decimal("2"), Decimal("20000")),
    "azn": (Decimal("2"), Decimal("20000")),
    "bbd": (Decimal("2"), Decimal("20000")),
    "bdt": (Decimal("200"), Decimal("2000000")),
    "brl": (Decimal("6"), Decimal("60000")),
    "cad": (Decimal("2"), Decimal("20000")),
    "chf": (Decimal("0.90"), Decimal("9000")),
    "cny": (Decimal("7"), Decimal("70000")),
    "cop": (Decimal("4000"), Decimal("40000000")),
    "czk": (Decimal("30"), Decimal("300000")),
    "dkk": (Decimal("7"), Decimal("70000")),
    "dop": (Decimal("70"), Decimal("700000")),
    "dzd": (Decimal("200"), Decimal("2000000")),
    "egp": (Decimal("60"), Decimal("600000")),
    "eur": (Decimal("1"), Decimal("10000")),
    "fjd": (Decimal("3"), Decimal("30000")),
    "gbp": (Decimal("0.80"), Decimal("8000")),
    "gel": (Decimal("3"), Decimal("30000")),
    "gyd": (Decimal("300"), Decimal("3000000")),
    "hkd": (Decimal("8"), Decimal("80000")),
    "idr": (Decimal("20000"), Decimal("200000000")),
    "inr": (Decimal("100"), Decimal("1000000")),
    "jmd": (Decimal("200"), Decimal("2000000")),
    "kes": (Decimal("200"), Decimal("2000000")),
    "lkr": (Decimal("400"), Decimal("4000000")),
    "mad": (Decimal("10"), Decimal("100000")),
    "mxn": (Decimal("20"), Decimal("200000")),
    "myr": (Decimal("5"), Decimal("50000")),
    "nad": (Decimal("20"), Decimal("200000")),
    "ngn": (Decimal("2000"), Decimal("20000000")),
    "nok": (Decimal("10"), Decimal("100000")),
    "npr": (Decimal("200"), Decimal("2000000")),
    "nzd": (Decimal("2"), Decimal("20000")),
    "pen": (Decimal("4"), Decimal("40000")),
    "php": (Decimal("70"), Decimal("700000")),
    "pkr": (Decimal("300"), Decimal("3000000")),
    "pln": (Decimal("4"), Decimal("40000")),
    "qar": (Decimal("4"), Decimal("40000")),
    "rsd": (Decimal("200"), Decimal("2000000")),
    "rub": (Decimal("90"), Decimal("900000")),
    "sar": (Decimal("4"), Decimal("40000")),
    "sek": (Decimal("20"), Decimal("200000")),
    "sgd": (Decimal("2"), Decimal("20000")),
    "thb": (Decimal("40"), Decimal("400000")),
    "try": (Decimal("60"), Decimal("600000")),
    "ttd": (Decimal("7"), Decimal("70000")),
    "uah": (Decimal("50"), Decimal("500000")),
    "usd": (Decimal("0.50"), Decimal("10000")),
    "uyu": (Decimal("50"), Decimal("500000")),
    "zar": (Decimal("20"), Decimal("200000")),
}

MAX_IMAGE_UPLOAD_SIZE_MB = 5

MAX_IMAGE_PIXELS = 25_000_000

ALLOWED_IMAGE_FORMATS = {"JPEG", "PNG", "WEBP"}

TEXT_JOINERS = "\u200c\u200d"

TEXT_ERROR = "This contains characters that aren't allowed."

NAME_PUNCTUATION = " '\u2019-."

TITLE_PUNCTUATION = " &'\u2019-\u2013:,.!?()/+#%"

REPEATED_PUNCTUATION = re.compile(r"([^\w\s])\1")
