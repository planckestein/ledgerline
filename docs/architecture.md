# Architecture

Ledgerline is a single Flask service backed by one relational database
(PostgreSQL in production, SQLite for development and tests) and a Celery
worker for periodic jobs.

```
             HTTPS (JSON)                      Celery beat
                  |                                 |
        +---------v----------+            +---------v----------+
        |  ledgerline.api    |            |  ledgerline.tasks  |
        |  auth, schemas,    |            |  billing cycle,    |
        |  pagination        |            |  payment retries   |
        +---------+----------+            +---------+----------+
                  |                                 |
                  +---------------+-----------------+
                                  |
        +-------------------------v--------------------------+
        |                 domain services                    |
        |  billing/   subscriptions, renewal, invoice_builder, |
        |             invoicing, discounts, tax, usage,      |
        |             periods, proration, pricing            |
        |  payments/  gateway, service, dunning              |
        +-------------------------+--------------------------+
                                  |
                       ledgerline.models (SQLAlchemy)
                                  |
                          PostgreSQL / SQLite
```

## Packages

| package | responsibility |
|---|---|
| `ledgerline.money`, `currency` | `Money` value object, currency exponents, rounding |
| `ledgerline.geo` | country normalization, legacy billing-address parser |
| `ledgerline.models` | SQLAlchemy models; no business logic beyond small properties |
| `ledgerline.billing` | periods, pricing, prorations, discounts, tax, invoice assembly and lifecycle, subscription lifecycle, renewals |
| `ledgerline.payments` | gateway adapters (`fake` for dev/test), collection, dunning |
| `ledgerline.api.serializers` | public JSON representations of API resources |
| `ledgerline.api` | Flask blueprint: authentication, validation, pagination, resources |
| `ledgerline.tasks` | Celery app and periodic jobs |
| `ledgerline.cli` | operator commands (`flask tenants ...`, `flask billing ...`) |

Dependencies point downwards only: `api`/`tasks` → services → models. The
services never import from `api`.

## Transactions

* **API views own the transaction.** A view calls services, then commits
  once. Services `flush()` but never `commit()`.
* **Jobs commit per unit of work** (one subscription, one invoice) so that
  one bad record cannot block the run.
* Error handlers roll the session back before rendering an error.

## Multi-tenancy

Every table carries `tenant_id` (directly or through its parent). The API
authenticates the API key, stores the tenant in `flask.g`, and every lookup
goes through `api.helpers.scoped()` / `get_or_404()`. A resource of another
tenant is indistinguishable from a missing one (404).

## Time

All domain code reads time from `ledgerline.clock.utcnow()`. Tests install a
`FrozenClock` (see `tests/support/fixtures.py`) and move it explicitly.

## Database migrations

Alembic via Flask-Migrate, in `migrations/`. Revisions use batch mode so they
run on SQLite, name every constraint, and must leave the schema identical to
the models — `tests/migrations/test_migrations.py` compares them with
Alembic's autogenerate diff and round-trips `downgrade base` / `upgrade head`.
