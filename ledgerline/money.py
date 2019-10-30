"""Money value object.

``Money`` wraps an integer amount of minor units together with its currency.
All arithmetic is exact; rounding happens only where explicitly requested and
always uses *round half away from zero* (``ROUND_HALF_UP`` in ``decimal``
terminology), which is what our invoices have always shown.
"""
import functools
from decimal import ROUND_HALF_UP, Decimal
from fractions import Fraction
from typing import Iterable, List, Sequence

from ledgerline.currency import exponent, normalize_currency


class CurrencyMismatchError(ValueError):
    pass


def round_half_up(value) -> int:
    """Round an int, Decimal or Fraction to the nearest integer, halves away from zero."""
    if isinstance(value, int):
        return value
    if isinstance(value, Decimal):
        return int(value.quantize(Decimal(1), rounding=ROUND_HALF_UP))
    fraction = Fraction(value)
    sign = -1 if fraction < 0 else 1
    magnitude = abs(fraction)
    whole = magnitude.numerator // magnitude.denominator
    if magnitude - whole >= Fraction(1, 2):
        whole += 1
    return sign * whole


@functools.total_ordering
class Money:
    __slots__ = ("amount", "currency")

    def __init__(self, amount: int, currency: str):
        if isinstance(amount, bool) or not isinstance(amount, int):
            raise TypeError("Money amounts must be integers of minor units, got %r" % (amount,))
        self.amount = amount
        self.currency = normalize_currency(currency)

    # -- construction ---------------------------------------------------------------------

    @classmethod
    def zero(cls, currency: str) -> "Money":
        return cls(0, currency)

    @classmethod
    def from_major(cls, value, currency: str) -> "Money":
        """Build from a major-unit value such as ``Decimal("10.05")`` USD."""
        scaled = Decimal(str(value)).scaleb(exponent(currency))
        return cls(round_half_up(scaled), currency)

    def to_major(self) -> Decimal:
        return Decimal(self.amount).scaleb(-exponent(self.currency))

    # -- arithmetic -----------------------------------------------------------------------

    def _check(self, other):
        if not isinstance(other, Money):
            raise TypeError("Expected Money, got %r" % (other,))
        if other.currency != self.currency:
            raise CurrencyMismatchError(
                "Cannot combine %s with %s" % (self.currency, other.currency)
            )

    def __add__(self, other):
        self._check(other)
        return Money(self.amount + other.amount, self.currency)

    def __sub__(self, other):
        self._check(other)
        return Money(self.amount - other.amount, self.currency)

    def __neg__(self):
        return Money(-self.amount, self.currency)

    def __abs__(self):
        return Money(abs(self.amount), self.currency)

    def multiply(self, factor) -> "Money":
        """Multiply by an int, Decimal or Fraction and round half up to a minor unit."""
        if isinstance(factor, float):
            raise TypeError("Floats are not accepted in money arithmetic; use Decimal")
        exact = Fraction(self.amount) * Fraction(factor)
        return Money(round_half_up(exact), self.currency)

    def percentage(self, percent) -> "Money":
        """Return ``percent`` % of this amount, e.g. ``Money(1000, 'usd').percentage(15)``."""
        return self.multiply(Fraction(Decimal(str(percent))) / 100)

    def allocate(self, weights: Sequence[int]) -> List["Money"]:
        """Split the amount proportionally to ``weights`` without losing a minor unit.

        Every share is rounded down and the leftover minor units go to the first
        shares, one each. The result always sums to
        ``self``.
        """
        weights = list(weights)
        if not weights:
            raise ValueError("allocate() needs at least one weight")
        if any(weight < 0 for weight in weights):
            raise ValueError("allocation weights must be non-negative")
        total_weight = sum(weights)
        if total_weight == 0:
            raise ValueError("allocation weights must not all be zero")

        sign = -1 if self.amount < 0 else 1
        magnitude = abs(self.amount)
        shares = []
        for weight in weights:
            shares.append(magnitude * weight // total_weight)
        leftover = magnitude - sum(shares)
        for index in range(leftover):
            shares[index] += 1
        return [Money(sign * share, self.currency) for share in shares]

    # -- comparison -----------------------------------------------------------------------

    def __eq__(self, other):
        if not isinstance(other, Money):
            return NotImplemented
        return self.amount == other.amount and self.currency == other.currency

    def __lt__(self, other):
        self._check(other)
        return self.amount < other.amount

    def __hash__(self):
        return hash((self.amount, self.currency))

    def __bool__(self):
        return self.amount != 0

    # -- presentation ---------------------------------------------------------------------

    def format(self) -> str:
        places = exponent(self.currency)
        return "%s %s" % (self.currency.upper(), format(self.to_major(), ".%df" % places))

    def __repr__(self):
        return "Money(%d, %r)" % (self.amount, self.currency)


def sum_money(values: Iterable[Money], currency: str) -> Money:
    total = Money.zero(currency)
    for value in values:
        total = total + value
    return total
