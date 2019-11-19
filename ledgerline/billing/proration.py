"""Proration helpers.

When a subscription changes mid-period we credit the unused part of the old
configuration and charge the remaining part of the new one. Each proration
line is rounded on its own (half away from zero).
"""
from fractions import Fraction

from ledgerline.money import round_half_up


def unused_fraction(period_start, period_end, at):
    """Fraction of the period ``[period_start, period_end)`` that remains after ``at``."""
    if at <= period_start:
        return Fraction(1)
    if at >= period_end:
        return Fraction(0)
    total_days = (period_end - period_start).days
    remaining_days = (period_end - at).days
    if total_days <= 0:
        return Fraction(0)
    return Fraction(remaining_days, total_days)


def prorate(amount, fraction):
    """Return ``amount * fraction`` rounded to a whole minor unit."""
    return round_half_up(Fraction(amount) * fraction)
