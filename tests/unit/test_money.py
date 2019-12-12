from decimal import Decimal
from fractions import Fraction

import pytest

from ledgerline.currency import UnknownCurrencyError, exponent, normalize_currency
from ledgerline.money import CurrencyMismatchError, Money, round_half_up, sum_money


class TestCurrency:
    def test_normalizes_case_and_whitespace(self):
        assert normalize_currency(" USD ") == "usd"

    def test_rejects_unknown_currency(self):
        with pytest.raises(UnknownCurrencyError):
            normalize_currency("xyz")

    @pytest.mark.parametrize("code,places", [("usd", 2), ("jpy", 0), ("kwd", 3), ("eur", 2)])
    def test_exponents(self, code, places):
        assert exponent(code) == places


class TestRoundHalfUp:
    @pytest.mark.parametrize(
        "value,expected",
        [
            (Fraction(5, 2), 3),
            (Fraction(-5, 2), -3),
            (Fraction(7, 3), 2),
            (Decimal("100.5"), 101),
            (Decimal("-0.5"), -1),
            (Decimal("0.4999"), 0),
            (42, 42),
        ],
    )
    def test_rounds_halves_away_from_zero(self, value, expected):
        assert round_half_up(value) == expected


class TestMoney:
    def test_requires_integer_minor_units(self):
        with pytest.raises(TypeError):
            Money(10.5, "usd")
        with pytest.raises(TypeError):
            Money(True, "usd")

    def test_arithmetic(self):
        assert Money(100, "usd") + Money(50, "usd") == Money(150, "usd")
        assert Money(100, "usd") - Money(150, "usd") == Money(-50, "usd")
        assert -Money(5, "eur") == Money(-5, "eur")

    def test_currency_mismatch(self):
        with pytest.raises(CurrencyMismatchError):
            Money(1, "usd") + Money(1, "eur")

    @pytest.mark.parametrize(
        "major,currency,minor",
        [
            ("10.05", "usd", 1005),
            ("1000", "jpy", 1000),
            ("1.234", "kwd", 1234),
            ("0.005", "usd", 1),
        ],
    )
    def test_from_major(self, major, currency, minor):
        assert Money.from_major(Decimal(major), currency).amount == minor

    def test_to_major_respects_exponent(self):
        assert Money(1234, "kwd").to_major() == Decimal("1.234")
        assert Money(500, "jpy").to_major() == Decimal("500")

    def test_percentage_rounds_half_up(self):
        assert Money(1005, "usd").percentage(10).amount == 101
        assert Money(1004, "usd").percentage(10).amount == 100
        assert Money(-1005, "usd").percentage(10).amount == -101
        assert Money(999, "usd").percentage(Decimal("33.333")).amount == 333

    def test_multiply_rejects_floats(self):
        with pytest.raises(TypeError):
            Money(100, "usd").multiply(0.5)

    def test_format(self):
        assert Money(1005, "usd").format() == "USD 10.05"
        assert Money(1500, "jpy").format() == "JPY 1500"
        assert Money(1234, "kwd").format() == "KWD 1.234"

    def test_comparison_and_hash(self):
        assert Money(1, "usd") < Money(2, "usd")
        assert len({Money(1, "usd"), Money(1, "usd")}) == 1
        assert not Money.zero("usd")

    def test_sum_money(self):
        assert sum_money([Money(1, "usd"), Money(2, "usd")], "usd") == Money(3, "usd")
        assert sum_money([], "usd") == Money(0, "usd")


class TestAllocate:
    def test_even_split_gives_leftover_to_first(self):
        shares = Money(100, "usd").allocate([1, 1, 1])
        assert [share.amount for share in shares] == [34, 33, 33]

    def test_proportional_split_sums_exactly(self):
        shares = Money(201, "usd").allocate([1005, 1005])
        assert [share.amount for share in shares] == [101, 100]
        shares = Money(1000, "usd").allocate([1, 2, 3, 4])
        assert sum(share.amount for share in shares) == 1000
        assert [share.amount for share in shares] == [100, 200, 300, 400]

    def test_largest_remainder_wins(self):
        # 10 * 3/7 = 4.28, 10 * 4/7 = 5.71 -> second share gets the leftover unit.
        shares = Money(10, "usd").allocate([3, 4])
        assert [share.amount for share in shares] == [4, 6]

    def test_negative_amounts(self):
        shares = Money(-100, "usd").allocate([1, 1, 1])
        assert [share.amount for share in shares] == [-34, -33, -33]

    def test_zero_weights_are_rejected(self):
        with pytest.raises(ValueError):
            Money(10, "usd").allocate([0, 0])
        with pytest.raises(ValueError):
            Money(10, "usd").allocate([])
        with pytest.raises(ValueError):
            Money(10, "usd").allocate([1, -1])
