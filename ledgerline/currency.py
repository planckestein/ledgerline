"""ISO 4217 currencies supported by Ledgerline and their minor-unit exponents.

Amounts are always stored as integers in the currency's *minor unit*
(cents for USD, yen for JPY, fils for KWD). See docs/adr/0001.
"""

CURRENCY_EXPONENTS = {
    "aud": 2,
    "bhd": 3,
    "cad": 2,
    "chf": 2,
    "eur": 2,
    "gbp": 2,
    "jod": 3,
    "jpy": 0,
    "krw": 0,
    "kwd": 3,
    "nok": 2,
    "omr": 3,
    "sek": 2,
    "try": 2,
    "usd": 2,
    "vnd": 0,
}


class UnknownCurrencyError(ValueError):
    pass


def normalize_currency(code):
    if not isinstance(code, str):
        raise UnknownCurrencyError("Currency must be a string, got %r" % (code,))
    normalized = code.strip().lower()
    if normalized not in CURRENCY_EXPONENTS:
        raise UnknownCurrencyError("Unsupported currency %r" % (code,))
    return normalized


def exponent(code):
    """Number of decimal places of the currency's minor unit."""
    return CURRENCY_EXPONENTS[normalize_currency(code)]


def minor_unit_factor(code):
    return 10 ** exponent(code)
