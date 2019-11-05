"""Country helpers and the legacy billing-address parser.

``customers.billing_address`` is a free-form TEXT column that has been written
by three generations of clients:

* **v1** (2018 dashboard): JSON with ``street``/``zip`` keys and English country
  *names*, e.g. ``{"street": "...", "zip": "10115", "country": "Germany"}``.
* **v2** (public API, 2019): JSON with ``line1``, ``line2``, ``city``, ``state``,
  ``postal_code`` and an ISO country code in any case, e.g. ``"de"``.
* **v3** (CSV importer): a plain, comma separated string such as
  ``"Hauptstr. 5, 10115 Berlin, DE"`` -- sometimes JSON-encoded a second time.

:func:`parse_legacy_address` is the single source of truth for how those
values are interpreted.
"""
import json
import re

ADDRESS_FIELDS = ("line1", "line2", "city", "state", "postal_code", "country")

EU_COUNTRIES = frozenset(
    "AT BE BG CY CZ DE DK EE ES FI FR GR HR HU IE IT LT LU LV MT NL PL PT RO SE SI SK".split()
)

# EU VAT numbers start with the member state's code, except Greece which uses "EL".
EU_VAT_PREFIXES = (EU_COUNTRIES - {"GR"}) | {"EL"}

_COUNTRY_ALIASES = {
    "uk": "GB",
    "el": "GR",
}

COUNTRY_NAMES = {
    "austria": "AT",
    "belgium": "BE",
    "canada": "CA",
    "denmark": "DK",
    "deutschland": "DE",
    "france": "FR",
    "germany": "DE",
    "great britain": "GB",
    "greece": "GR",
    "ireland": "IE",
    "italy": "IT",
    "japan": "JP",
    "kuwait": "KW",
    "netherlands": "NL",
    "the netherlands": "NL",
    "poland": "PL",
    "spain": "ES",
    "sweden": "SE",
    "switzerland": "CH",
    "turkey": "TR",
    "united kingdom": "GB",
    "united states": "US",
    "united states of america": "US",
    "usa": "US",
}

_POSTAL_CITY = re.compile(r"^(?P<postal>\d[\d\- ]*\d|\d)\s+(?P<city>\D.*)$")


def normalize_country(value):
    """Return an upper-case ISO 3166-1 alpha-2 code, or ``None`` if unknown."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    lowered = text.lower()
    if lowered in _COUNTRY_ALIASES:
        return _COUNTRY_ALIASES[lowered]
    if len(text) == 2 and text.isalpha():
        return text.upper()
    return COUNTRY_NAMES.get(lowered)


def is_eu(country):
    return country is not None and country.upper() in EU_COUNTRIES


def empty_address():
    return dict.fromkeys(ADDRESS_FIELDS)


def _clean(value):
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _parse_freeform(text):
    parts = [part.strip() for part in text.split(",") if part.strip()]
    address = empty_address()
    if not parts:
        return address
    if len(parts) >= 2:
        country = normalize_country(parts[-1])
        if country:
            address["country"] = country
            parts = parts[:-1]
    address["line1"] = parts[0]
    if len(parts) >= 2:
        locality = parts[-1]
        match = _POSTAL_CITY.match(locality)
        if match:
            address["postal_code"] = match.group("postal")
            address["city"] = match.group("city").strip()
        else:
            address["city"] = locality
        middle = parts[1:-1]
        if middle:
            address["line2"] = ", ".join(middle)
    return address


def parse_legacy_address(raw):
    """Parse any historical ``billing_address`` value into a dict of ADDRESS_FIELDS."""
    if raw is None:
        return empty_address()
    if isinstance(raw, str):
        text = raw.strip()
        if not text or text.lower() == "null":
            return empty_address()
        try:
            data = json.loads(text)
        except ValueError:
            return _parse_freeform(text)
    else:
        data = raw

    if isinstance(data, str):
        return _parse_freeform(data)
    if not isinstance(data, dict):
        return empty_address()

    address = empty_address()
    address["line1"] = _clean(data.get("line1") or data.get("street"))
    address["line2"] = _clean(data.get("line2"))
    address["city"] = _clean(data.get("city"))
    address["state"] = _clean(data.get("state") or data.get("region"))
    address["postal_code"] = _clean(data.get("postal_code") or data.get("zip"))
    address["country"] = normalize_country(data.get("country") or data.get("country_code"))
    return address


def serialize_address(address):
    """Serialize an address dict into the canonical (v2) storage format."""
    if not address or not any(address.get(field) for field in ADDRESS_FIELDS):
        return None
    payload = {field: address.get(field) for field in ADDRESS_FIELDS if address.get(field)}
    if payload.get("country"):
        payload["country"] = normalize_country(payload["country"])
    return json.dumps(payload, sort_keys=True)
