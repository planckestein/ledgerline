# LL-107: Migration: structured billing addresses and tax IDs

| | |
|---|---|
| **Type** | Database migration (schema + data) + refactoring |
| **Difficulty** | Very hard |
| **Areas** | Alembic data migration, customer model, tax engine, API, test support |
| **Verify** | `python scripts/verify_task.py LL-107` |

## Motivation

`customers.billing_address` is a free-form TEXT column written by three
generations of clients (see the module docstring of `ledgerline/geo.py`), and
`customers.vat_id` is free text. Every tax calculation re-parses the address,
reporting cannot filter by country, and a VAT id from the wrong country still
triggers EU reverse charge. We want structured columns and typed tax IDs.

## Target schema

**`customers`** gains six nullable columns and loses two:

| new column | type |
|---|---|
| `address_line1`, `address_line2` | `VARCHAR(200)` |
| `address_city`, `address_state` | `VARCHAR(100)` |
| `address_postal_code` | `VARCHAR(20)` |
| `address_country` | `VARCHAR(2)` (upper-case ISO 3166-1 alpha-2) |

`billing_address` and `vat_id` are **dropped**.

**`customer_tax_ids`** (new): `id`, `public_id` (prefix `txi_`, unique),
`tenant_id` (FK, indexed), `customer_id` (FK, indexed), `type`
(`VARCHAR(20)`, not null), `value` (`VARCHAR(64)`, not null), `created_at`;
unique on `(customer_id, value)`.

## Data migration rules

Production contains every historical format. The new revision must convert
every row:

* **Address**: the six columns must hold exactly what
  `ledgerline.geo.parse_legacy_address(billing_address)` returns today for
  that row (fields map to `address_<field>`). All-empty results leave all
  columns NULL.
* **Tax IDs**: for every non-empty `vat_id`, normalize the value
  (remove whitespace, `.` and `-`; upper-case). If nothing is left, create no
  tax ID. Otherwise create one tax ID whose `type` is
  * `ch_vat` if the value starts with `CHE`,
  * `gb_vat` if it starts with `GB`,
  * `eu_vat` if it starts with an EU VAT prefix (the member-state codes,
    with **`EL`** for Greece — see `EU_VAT_PREFIXES`),
  * `unknown` otherwise.
* The migration must be **self-contained**: it must not import anything from
  the `ledgerline` package (application code changes after a migration is
  written; the migration must keep producing the same result forever).
* It must run on SQLite and PostgreSQL and process rows in batches (do not
  load the whole table into memory at once).
* **Downgrade** restores `billing_address` in the canonical v2 JSON format
  produced by `geo.serialize_address` (sorted keys, only non-empty fields) or
  NULL when the address is empty, and restores `vat_id` from the customer's
  first tax ID (lowest id) or NULL, then drops the new table and columns.

`tasks/LL-107-structured-billing-addresses/fixtures/legacy_customers.json`
contains a representative sample of production rows with the expected
results.

## Application changes

* `Customer` uses the new columns; nothing reads or writes the legacy
  columns any more. The public API stays backward compatible:
  * `POST /v1/customers`, `POST /v1/customers/:id` and `POST /v1/customers/import`
    still accept `address` (object) and `vat_id` (string). Setting `vat_id`
    replaces the customer's tax IDs with one normalized tax ID (same rules as
    above); `null` or an empty string removes all tax IDs.
  * Customer objects still return `address` (all six keys) and `vat_id`
    (value of the first tax ID or `null`), and gain
    `tax_ids: [{"id": "txi_...", "type": "eu_vat", "value": "DE811907980"}]`.
* Tax resolution reads the structured address. **EU reverse charge** now
  requires a tax ID of type `eu_vat` (any other type does not qualify).
* `tests/support/factories.py` and any other test helpers must be adapted
  to the new model; existing tests must keep their meaning.

## Acceptance criteria

1. All tests in `tasks/LL-107-structured-billing-addresses/tests/` pass.
2. The full regression suite (`python -m pytest tests`) passes, including the
   migration drift and round-trip tests.
3. One new migration head on top of `f3b9d2e6a399`.
4. No existing test is deleted or weakened; `make lint` passes.
