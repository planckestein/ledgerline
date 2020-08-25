# Billing model

This document is the **specification** of how Ledgerline computes money. When
code and this document disagree, the document wins and the code has a bug.
Every rule here is referenced from the code and from the test suite.

All amounts are integers in the currency's minor unit (see
[ADR 0001](adr/0001-integer-minor-units.md)). All datetimes are naive UTC.
Unless stated otherwise, rounding is **half away from zero** to one minor
unit (`ledgerline.money.round_half_up`).

---

## 1. Billing periods

A subscription has a `billing_cycle_anchor`. Period boundaries are derived
**from the anchor**, never from the previous boundary:

```
boundary(n) = anchor + n × (interval × interval_count)      n = 0, 1, 2, ...
period(n)   = [boundary(n), boundary(n + 1))
```

Month and year arithmetic clamps the day to the last day of the target month,
but the clamp is applied to each boundary independently. A subscription
anchored on **2020-01-31 10:00** (monthly) therefore has these boundaries:

| n | boundary            |
|---|---------------------|
| 0 | 2020-01-31 10:00    |
| 1 | 2020-02-29 10:00    |
| 2 | 2020-03-31 10:00    |
| 3 | 2020-04-30 10:00    |
| 4 | 2020-05-31 10:00    |

A yearly subscription anchored on 2020-02-29 renews on 2021-02-28,
2022-02-28, 2023-02-28 and **2024-02-29**.

**Trials.** A subscription created with a trial has
`current_period = [created_at, trial_end)` and `billing_cycle_anchor = trial_end`;
regular periods start at the trial end.

**Renewal** (`ledgerline.billing.renewal`) runs when
`now >= current_period_end`. One invoice is created per elapsed period; the
licensed items are charged **in advance** for the new period and metered items
are charged **in arrears** for the period that just ended.

## 2. Prorations

When licensed items change mid-period (`update_subscription_items`), the unused
part of the old configuration is credited and the remaining part of the new
configuration is charged, as pending invoice items with `proration=True`:

```
fraction = (period_end - change_time) / (period_end - period_start)   # in seconds
credit   = -round(old_amount × fraction)
charge   =  round(new_amount × fraction)
```

* The fraction is computed **to the second** (not in whole days).
* Each proration item is rounded on its own.
* Metered items and trialing subscriptions are never prorated.
* `proration_behavior="always_invoice"` bills the prorations immediately;
  `"none"` creates no prorations.

## 3. Discounts

At most one discount applies to an invoice: a subscription discount wins over
a customer discount. A discount is active for an invoice if
`discount.start <= reference < discount.end` where `reference` is the
invoice's `period_start` (or the current time for manual invoices).

* `once` — the first invoice only. `repeating` — `duration_in_months` months
  from the start. `forever` — no end.
* Only lines with a **positive amount** are discountable.

**Allocation.** The invoice-level discount is computed first and then
allocated across the discountable lines in proportion to their amounts using
the largest-remainder method (`Money.allocate`); ties go to the earlier line:

```
percent_off:  discount_total = round(discountable_subtotal × percent_off / 100)
amount_off:   discount_total = min(amount_off, discountable_subtotal)   # same currency only
line.discount_amount = allocation of discount_total     # sum(lines) == discount_total
```

Example: two lines of 10.05 USD and a 10 % coupon: `discount_total = 2.01`,
allocated as `1.01` and `1.00` (not `1.01 + 1.01`).

## 4. Tax

Rate selection is documented in `ledgerline/billing/tax.py`
(exempt → EU reverse charge → country+state → country → global).

Tax is computed **per line on the net amount** (`amount - discount_amount`)
in the currency's minor units and rounded half away from zero to **one minor
unit of that currency** — 1 cent for EUR, 1 yen for JPY, 1 fils for KWD:

```
exclusive: tax = round(net × p / 100)              line contributes net + tax
inclusive: tax = net - round(net / (1 + p / 100))  line contributes net
```

## 5. Invoice invariants

After `finalize_invoice` the following always hold:

```
subtotal       == Σ line.amount
discount_total == Σ line.discount_amount
tax_total      == Σ line.tax_amount
total          == subtotal - discount_total + Σ tax_amount of exclusive lines
amount_due     == total - amount_paid           (never negative)
```

A finalized invoice gets the number `<customer.invoice_prefix>-<NNNN>`; the
sequence is per customer and never reused.

Invoice states: `draft → open → paid`, `draft|open → void`,
`open → uncollectible → paid`. Any other transition raises
`InvalidStateTransition` (HTTP 409).

## 6. Ledger postings

See [ADR 0003](adr/0003-double-entry-ledger.md). Every entry balances; an
unbalanced entry raises `LedgerImbalanceError`, aborting the transaction.

| event                | debit                          | credit                              |
|----------------------|--------------------------------|-------------------------------------|
| invoice finalized    | AR `total`                     | revenue `Σ(net − inclusive tax)`, tax payable `tax_total` |
| payment              | cash                           | AR                                  |
| invoice voided       | revenue, tax payable           | AR                                  |
| marked uncollectible | bad debt                       | AR                                  |
| write-off recovered  | AR                             | bad debt                            |

## 7. Payments and dunning

Automatic collection charges the customer's default payment method once when
an invoice is finalized. On failure the tenant's `dunning_retry_days`
(`"3,5,7"`) schedules retries, each counted from the previous attempt. After
the last retry `dunning_final_action` cancels the subscription (invoice →
uncollectible) or marks it `unpaid`. The first invoice of a subscription is
not retried; the subscription stays `incomplete` until it is paid.

## 8. API conventions

**Pagination.** Lists are ordered newest first by `(created_at, id)`. The
order is total: objects created in the same instant (bulk imports, frozen
clocks) are still returned exactly once while paging with `starting_after` /
`ending_before`. `has_more` is `true` if and only if at least one more object
exists beyond the returned page in the direction of travel.
