from datetime import datetime
from fractions import Fraction

import pytest

from ledgerline.billing import periods, proration


class TestAddMonths:
    @pytest.mark.parametrize(
        "start,months,expected",
        [
            (datetime(2020, 1, 15, 8), 1, datetime(2020, 2, 15, 8)),
            (datetime(2020, 1, 31, 8), 1, datetime(2020, 2, 29, 8)),
            (datetime(2021, 1, 31, 8), 1, datetime(2021, 2, 28, 8)),
            (datetime(2020, 3, 31), 1, datetime(2020, 4, 30)),
            (datetime(2020, 11, 30), 3, datetime(2021, 2, 28)),
            (datetime(2020, 12, 15), 1, datetime(2021, 1, 15)),
            (datetime(2020, 2, 29), 12, datetime(2021, 2, 28)),
        ],
    )
    def test_clamps_to_month_end(self, start, months, expected):
        assert periods.add_months(start, months) == expected


class TestShift:
    def test_day_and_week(self):
        assert periods.shift(datetime(2020, 6, 1), "day", 3) == datetime(2020, 6, 4)
        assert periods.shift(datetime(2020, 6, 1), "week", 2) == datetime(2020, 6, 15)

    def test_year(self):
        assert periods.shift(datetime(2020, 6, 1), "year", 1) == datetime(2021, 6, 1)

    def test_unknown_interval(self):
        with pytest.raises(ValueError):
            periods.shift(datetime(2020, 6, 1), "fortnight", 1)


class TestValidateInterval:
    @pytest.mark.parametrize("interval,count", [("month", 12), ("week", 52), ("year", 1)])
    def test_accepts_up_to_one_year(self, interval, count):
        periods.validate_interval(interval, count)

    @pytest.mark.parametrize(
        "interval,count", [("month", 13), ("year", 2), ("day", 0), ("hour", 1), ("month", "1")]
    )
    def test_rejects_invalid(self, interval, count):
        with pytest.raises(ValueError):
            periods.validate_interval(interval, count)


class TestPeriods:
    def test_initial_period(self):
        anchor = datetime(2020, 6, 15, 9, 30)
        assert periods.initial_period(anchor, "month", 1) == (anchor, datetime(2020, 7, 15, 9, 30))

    def test_next_period_mid_month(self):
        start, end = periods.next_period(datetime(2020, 7, 15, 9, 30), "month", 1)
        assert start == datetime(2020, 7, 15, 9, 30)
        assert end == datetime(2020, 8, 15, 9, 30)

    def test_next_period_quarterly(self):
        start, end = periods.next_period(datetime(2020, 4, 10), "month", 3)
        assert (start, end) == (datetime(2020, 4, 10), datetime(2020, 7, 10))


class TestProration:
    start = datetime(2020, 6, 1, 12)
    end = datetime(2020, 7, 1, 12)

    def test_full_and_empty(self):
        assert proration.unused_fraction(self.start, self.end, self.start) == 1
        assert proration.unused_fraction(self.start, self.end, self.end) == 0
        assert proration.unused_fraction(self.start, self.end, datetime(2020, 5, 1)) == 1

    def test_half_period(self):
        assert proration.unused_fraction(
            self.start, self.end, datetime(2020, 6, 16, 12)
        ) == Fraction(1, 2)

    def test_prorate_rounds_each_amount(self):
        assert proration.prorate(1000, Fraction(1, 3)) == 333
        assert proration.prorate(1000, Fraction(2, 3)) == 667
        assert proration.prorate(-1000, Fraction(2, 3)) == -667
