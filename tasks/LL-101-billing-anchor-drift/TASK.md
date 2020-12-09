# LL-101: Month-end subscriptions drift, prorations ignore the time of day

| | |
|---|---|
| **Type** | Bug fix (multi-cause) |
| **Difficulty** | Hard |
| **Areas** | billing periods, renewals, prorations, trials |
| **Verify** | `python scripts/verify_task.py LL-101` |

## Report

> **From:** Finance operations · **Severity:** high
>
> 1. Customers who signed up on the 31st of a month are billed on the 29th of
>    every month after February. Example: `sub_…` started **2020-01-31 10:00**,
>    renewed on 2020-02-29 (correct), but then on **2020-03-29**, 2020-04-29,
>    2020-05-29… It should have renewed on 2020-03-31, 2020-04-30, 2020-05-31.
>    The same happens to quarterly plans and to yearly plans started on
>    29 February, and to trials that end on a month end.
> 2. Our spreadsheet never matches the proration credits. A customer upgraded
>    from 1 to 2 seats (9.99 EUR/seat/month) on 2020-06-10 at 18:30 in a period
>    running 2020-06-01 12:00 → 2020-07-01 12:00. We expected a credit of
>    **-6.90** and a charge of **13.81**; Ledgerline produced -6.66 and 13.32.
>    Daily plans changed on the day of purchase get no proration at all.

## Expected behaviour

The billing specification is [docs/billing-model.md](../../docs/billing-model.md),
sections 1 (billing periods) and 2 (prorations). In short:

* Every period boundary is computed from `billing_cycle_anchor`:
  `boundary(n) = anchor + n × interval`, clamping each boundary to the end of
  its month independently. Clamping must never "stick" to later periods.
* For trials, the anchor is the trial end.
* When the renewal job catches up on several missed periods, every one of
  them must be anchor-aligned.
* Proration fractions are computed **to the second**:
  `(period_end - change_time) / (period_end - period_start)`.
  Each proration line is rounded half away from zero.
* Behaviour for anchors that do not need clamping (e.g. the 1st or 15th of a
  month) must not change.

## Acceptance criteria

1. All tests in `tasks/LL-101-billing-anchor-drift/tests/` pass.
2. The full regression suite (`python -m pytest tests`) passes.
3. No existing test is deleted or weakened. You may add tests.
4. No new third-party dependencies; the code must stay compatible with the
   pinned 2020 toolchain (Python 3.8, SQLAlchemy 1.3, …).
5. `make lint` (flake8, black, isort) passes.

## Notes

* Existing subscriptions whose `current_period_end` has already drifted do
  not need to be repaired by a data migration; it is enough that new
  boundaries are computed correctly from the anchor.
* Think about every code path that creates a period, not only the renewal
  job.
