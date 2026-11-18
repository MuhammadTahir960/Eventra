from importlib import resources

from apps.common.constants import CURRENCY_PRICE_LIMITS

COUNTRY_CURRENCIES = {
    "AE": "aed",
    "AR": "ars",
    "AT": "eur",
    "AU": "aud",
    "AZ": "azn",
    "BB": "bbd",
    "BD": "bdt",
    "BE": "eur",
    "BR": "brl",
    "CA": "cad",
    "CH": "chf",
    "CN": "cny",
    "CO": "cop",
    "CZ": "czk",
    "DE": "eur",
    "DK": "dkk",
    "DO": "dop",
    "DZ": "dzd",
    "EC": "usd",
    "EG": "egp",
    "ES": "eur",
    "FI": "eur",
    "FJ": "fjd",
    "FR": "eur",
    "GB": "gbp",
    "GE": "gel",
    "GR": "eur",
    "GY": "gyd",
    "HK": "hkd",
    "HR": "eur",
    "ID": "idr",
    "IE": "eur",
    "IN": "inr",
    "IT": "eur",
    "JM": "jmd",
    "KE": "kes",
    "LK": "lkr",
    "MA": "mad",
    "MC": "eur",
    "MX": "mxn",
    "MY": "myr",
    "NA": "nad",
    "NG": "ngn",
    "NL": "eur",
    "NO": "nok",
    "NP": "npr",
    "NZ": "nzd",
    "PE": "pen",
    "PH": "php",
    "PK": "pkr",
    "PL": "pln",
    "PT": "eur",
    "QA": "qar",
    "RS": "rsd",
    "RU": "rub",
    "SA": "sar",
    "SE": "sek",
    "SG": "sgd",
    "TH": "thb",
    "TR": "try",
    "TT": "ttd",
    "UA": "uah",
    "US": "usd",
    "UY": "uyu",
    "ZA": "zar",
    "ZW": "usd",
}

COUNTRY_CODES = list(COUNTRY_CURRENCIES)


def _read_country_time_zones() -> dict[str, list[str]]:
    zones = {code: [] for code in COUNTRY_CODES}
    table = resources.files("tzdata.zoneinfo").joinpath("zone.tab")
    for line in table.read_text(encoding="utf-8").splitlines():
        if line.startswith("#"):
            continue
        code, _coordinates, zone = line.split("\t")[:3]
        if code in zones:
            zones[code].append(zone)
    return zones


COUNTRY_TIME_ZONES = _read_country_time_zones()

COUNTRIES = [
    {
        "code": code,
        "time_zones": zones,
        "currency": COUNTRY_CURRENCIES[code],
        "min_price": str(CURRENCY_PRICE_LIMITS[COUNTRY_CURRENCIES[code]][0]),
        "max_price": str(CURRENCY_PRICE_LIMITS[COUNTRY_CURRENCIES[code]][1]),
    }
    for code, zones in COUNTRY_TIME_ZONES.items()
]
