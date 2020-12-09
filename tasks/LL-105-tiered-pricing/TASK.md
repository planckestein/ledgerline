# LL-105: Feature: tiered pricing (graduated and volume)

| | |
|---|---|
| **Type** | Feature + database migration |
| **Difficulty** | Hard |
| **Areas** | catalog model, pricing, invoices, prorations, API validation, Alembic |
| **Verify** | `python scripts/verify_task.py LL-105` |

## Motivation

Two of our largest merchants sell API calls with volume discounts and seats
with cheaper rates above a threshold. Today they emulate this with several
prices and manual credits. We want first-class tiered prices, modelled on the
industry-standard semantics below.

## Specification

### API

`POST /v1/prices` accepts a third billing scheme:

```json
{
  "product": "prod_...",
  "currency": "eur",
  "billing_scheme": "tiered",
  "tiers_mode": "graduated",
  "tiers": [
    {"up_to": 1000, "unit_amount": 10},
    {"up_to": 5000, "unit_amount": 7},
    {"up_to": "inf", "unit_amount": 5, "flat_amount": 1000}
  ],
  "recurring": {"interval": "month", "usage_type": "metered"}
}
```

* `tiers_mode` (`graduated` | `volume`) and `tiers` are **required** when
  `billing_scheme` is `tiered` and **rejected** otherwise.
* `unit_amount` must be omitted (or `null`) for tiered prices and stays
  required for `per_unit` and `package` prices.
* Each tier has `up_to` (positive integer, or the string `"inf"`),
  `unit_amount` (integer ≥ 0, default 0) and `flat_amount` (integer ≥ 0,
  default 0).
* Between 1 and 25 tiers; `up_to` strictly increasing; the **last** tier, and
  only the last tier, has `up_to: "inf"`.
* Validation errors are `400 invalid_request_error`. The `param` is the
  offending top-level field (`tiers_mode`, `unit_amount`, `tiers`); errors
  inside the tier list have a `param` starting with `tiers`.

Price objects (create, retrieve, list) gain two fields:

* `tiers_mode`: `"graduated"`, `"volume"` or `null`;
* `tiers`: `null` for non-tiered prices, otherwise the tiers in order as
  `{"up_to": <int or null>, "unit_amount": <int>, "flat_amount": <int>}`
  (`null` represents `"inf"`).

`unit_amount` is `null` for tiered prices.

### Amounts

For a quantity `q` (seats for licensed prices, aggregated usage for metered
prices):

* **graduated** — each tier charges the units that fall inside it:
  `Σ units_in_tier × unit_amount + flat_amount (if units_in_tier > 0)`.
* **volume** — the tier that contains `q` (the first tier with
  `up_to >= q`) prices *all* units: `q × unit_amount + flat_amount`.
* `q = 0` costs 0 in both modes.

Example with the tiers above: graduated 6 200 units →
`1000×10 + 4000×7 + (1200×5 + 1000) = 45 000`; volume 6 200 units →
`6200×5 + 1000 = 32 000`.

Tiered prices must work everywhere prices are used: first invoices and
renewals (licensed in advance, metered in arrears), quantity changes and
their prorations (prorate the tiered amount of the old/new quantity),
discounts and tax. Each subscription item still produces exactly **one**
invoice line whose `amount` is the tiered amount and whose `quantity` is `q`.

### Storage

* New table `price_tiers`: `id`, `price_id` (FK, indexed), `position`,
  `up_to` (nullable = infinity), `unit_amount`, `flat_amount`; unique on
  `(price_id, position)`.
* `prices.tiers_mode` (nullable string) and `prices.unit_amount` becomes
  nullable.
* Ship an Alembic migration that works on SQLite and PostgreSQL, keeps
  existing prices intact and has a working `downgrade()` (for databases that
  contain no tiered prices).

## Acceptance criteria

1. All tests in `tasks/LL-105-tiered-pricing/tests/` pass.
2. The full regression suite (`python -m pytest tests`) passes — including
   the migration drift test.
3. `per_unit` and `package` behaviour is unchanged.
4. Docs: describe tiered pricing in `docs/billing-model.md` and the new fields
   in `docs/api.md`.
5. No existing test is deleted or weakened; `make lint` passes.
