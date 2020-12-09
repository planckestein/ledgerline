# LL-104: List endpoints skip and repeat records; invoice list times out

| | |
|---|---|
| **Type** | Bug fix + performance |
| **Difficulty** | Medium–Hard |
| **Areas** | API pagination, SQLAlchemy loading strategies, serializers |
| **Verify** | `python scripts/verify_task.py LL-104` |

## Report

> **From:** Merchant support
>
> 1. A merchant imported 25 customers with `POST /v1/customers/import` and then
>    synced them with `GET /v1/customers?limit=10` following `starting_after`.
>    Their sync stopped after the **first page**; only 10 customers arrived.
>    With `ending_before` they get the same customers twice.
> 2. Another merchant with exactly 20 subscriptions pages with `limit=10` and
>    their client always requests a third, empty page because the second page
>    says `"has_more": true`.
> 3. `GET /v1/invoices?limit=100` takes several seconds for merchants with
>    multi-line invoices. Our APM shows hundreds of SQL statements per request.

## Expected behaviour

See docs/billing-model.md §8 ("Pagination") and docs/api.md.

* List order is newest first by `(created_at, id)` — a **total** order.
  Walking all pages with `starting_after` (or backwards with `ending_before`)
  returns every object exactly once, even when many objects share the same
  `created_at`.
* `has_more` is `true` if and only if at least one more object exists beyond
  the page in the direction of travel.
* The behaviour must be the same for every list endpoint (customers,
  products, prices, tax rates, coupons, subscriptions, invoices, invoice
  items, payment methods, webhook endpoints, events).
* Listing must use a constant number of SQL statements, independent of the
  number of objects on the page:

  | request | max SQL statements (including authentication) |
  |---|---|
  | `GET /v1/invoices?limit=100` | 10 |
  | `GET /v1/subscriptions?limit=100` | 8 |
  | `GET /v1/customers?limit=100` | 5 |

* Response bodies must not change.

## Acceptance criteria

1. All tests in `tasks/LL-104-pagination-and-n-plus-one/tests/` pass.
2. The full regression suite (`python -m pytest tests`) passes on SQLite, and
   the solution must not rely on SQLite-only behaviour (PostgreSQL is used in
   production).
3. No existing test is deleted or weakened; `make lint` passes.
