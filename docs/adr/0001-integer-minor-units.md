# ADR 0001: Store money as integer minor units

**Status:** accepted

## Context

Early prototypes stored amounts as `NUMERIC(12, 2)` major units. That broke as
soon as we billed in JPY (no decimals) and KWD (three decimals), and every
arithmetic step had to remember to quantize.

## Decision

* Every amount column is an `INTEGER` of the currency's minor unit.
* The exponent of each currency lives in `ledgerline/currency.py`; nothing
  else may assume "two decimals".
* Arithmetic goes through `ledgerline.money.Money`. Floats are rejected.
* Rounding is explicit and always half away from zero.
* Splitting an amount (discounts across lines) uses `Money.allocate`, which
  never creates or loses a minor unit.

## Consequences

* Converting to major units is only needed for display.
* Percentages (tax rates, coupons) are stored as `NUMERIC` and applied with
  exact `Fraction` arithmetic before a single rounding step.
