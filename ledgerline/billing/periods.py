"""Billing period arithmetic.

Month and year intervals clamp to the last day of shorter months, so a
subscription anchored on January 31st renews on February 28th (or 29th).
See docs/billing-model.md, "Billing periods", for the full rules.
"""
import calendar
from datetime import timedelta

INTERVALS = ("day", "week", "month", "year")

# Longest period we allow for each interval unit (one year).
MAX_INTERVAL_COUNT = {"day": 365, "week": 52, "month": 12, "year": 1}


def validate_interval(interval, interval_count):
    if interval not in INTERVALS:
        raise ValueError("interval must be one of %s" % ", ".join(INTERVALS))
    if isinstance(interval_count, bool) or not isinstance(interval_count, int):
        raise ValueError("interval_count must be an integer")
    if interval_count < 1 or interval_count > MAX_INTERVAL_COUNT[interval]:
        raise ValueError(
            "interval_count for %s must be between 1 and %d"
            % (interval, MAX_INTERVAL_COUNT[interval])
        )


def add_months(moment, months):
    """Add calendar months, clamping the day to the end of the target month."""
    month_index = moment.month - 1 + months
    year = moment.year + month_index // 12
    month = month_index % 12 + 1
    day = min(moment.day, calendar.monthrange(year, month)[1])
    return moment.replace(year=year, month=month, day=day)


def shift(moment, interval, count):
    """Move ``moment`` forward by ``count`` units of ``interval``."""
    if interval == "day":
        return moment + timedelta(days=count)
    if interval == "week":
        return moment + timedelta(weeks=count)
    if interval == "month":
        return add_months(moment, count)
    if interval == "year":
        return add_months(moment, 12 * count)
    raise ValueError("Unknown interval %r" % (interval,))


def initial_period(anchor, interval, interval_count):
    """The first ``(start, end)`` period of a subscription anchored at ``anchor``."""
    return anchor, shift(anchor, interval, interval_count)


def next_period(current_period_end, interval, interval_count):
    """The ``(start, end)`` period that follows a period ending at ``current_period_end``."""
    return current_period_end, shift(current_period_end, interval, interval_count)


def describe(start, end):
    return "%s - %s" % (start.strftime("%b %d, %Y"), end.strftime("%b %d, %Y"))
