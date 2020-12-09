# LL-102: Discounted invoices fail to finalize; JPY and KWD tax is wrong

| | |
|---|---|
| **Type** | Bug fix (multi-cause) |
| **Difficulty** | Medium–Hard |
| **Areas** | discounts, tax, invoice totals, ledger |
| **Verify** | `python scripts/verify_task.py LL-102` |

## Report

> **From:** On-call (two incidents merged into one ticket)
>
> **Incident A.** Since we launched the `LAUNCH10` coupon (10 % off, forever),
> some subscription sign-ups fail with HTTP 500 and the log says:
>
> ```
> Internal invariant violated: Journal entry for invoice in_… does not balance
> (debits=1808, credits=1809)
> ```
>
> It only happens for some baskets, e.g. two seats on two different 10.05 EUR
> prices. Retrying does not help. Manually created invoices with a percentage
> coupon fail the same way when they are finalized.
>
> **Incident B.** Our Japanese merchant reports that a 1,000 JPY plan with 10 %
> consumption tax was invoiced with **10,000 JPY** of tax. A Kuwaiti merchant
> says 5 % VAT on 1.234 KWD shows as 0.006 KWD instead of 0.062 KWD.

## Expected behaviour

See [docs/billing-model.md](../../docs/billing-model.md) sections 3 (discounts),
4 (tax) and 5 (invoice invariants), and
[ADR 0001](../../docs/adr/0001-integer-minor-units.md).

* The invoice-level discount is computed once and **allocated** across the
  discountable lines with the largest-remainder method; ties go to the
  earlier line. `discount_total == Σ line.discount_amount` always holds.
* Tax is rounded to one minor unit of the invoice currency (0 decimals for
  JPY, 3 for KWD, 2 for EUR/USD), half away from zero.
* Every finalized invoice satisfies the invariants in section 5 and posts a
  balanced journal entry. The trial balance stays balanced.
* Amount-off coupons, inclusive tax and EUR/USD exclusive tax already behave
  correctly and must keep doing so.

## Acceptance criteria

1. All tests in `tasks/LL-102-discount-tax-rounding/tests/` pass.
2. The full regression suite (`python -m pytest tests`) passes.
3. No existing test is deleted or weakened. You may add tests.
4. Do **not** weaken the ledger's imbalance check: fix the numbers, not the
   guard.
5. No new dependencies; `make lint` passes.
