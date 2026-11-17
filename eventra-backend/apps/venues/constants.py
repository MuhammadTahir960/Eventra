from importlib import resources

COUNTRY_CODES = [
    "AE",
    "AR",
    "AT",
    "AU",
    "AZ",
    "BB",
    "BD",
    "BE",
    "BR",
    "CA",
    "CH",
    "CN",
    "CO",
    "CZ",
    "DE",
    "DK",
    "DO",
    "DZ",
    "EC",
    "EG",
    "ES",
    "FI",
    "FJ",
    "FR",
    "GB",
    "GE",
    "GR",
    "GY",
    "HK",
    "HR",
    "ID",
    "IE",
    "IN",
    "IT",
    "JM",
    "KE",
    "LK",
    "MA",
    "MC",
    "MX",
    "MY",
    "NA",
    "NG",
    "NL",
    "NO",
    "NP",
    "NZ",
    "PE",
    "PH",
    "PK",
    "PL",
    "PT",
    "QA",
    "RS",
    "RU",
    "SA",
    "SE",
    "SG",
    "TH",
    "TR",
    "TT",
    "UA",
    "US",
    "UY",
    "ZA",
    "ZW",
]


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
    {"code": code, "time_zones": zones} for code, zones in COUNTRY_TIME_ZONES.items()
]
