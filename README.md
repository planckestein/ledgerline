# Ledgerline

Ledgerline is a multi-tenant **subscription billing service**: merchants
(tenants) define products and recurring prices, subscribe their customers, and
Ledgerline takes care of billing periods, prorations, coupons, tax, invoices
and card payments with dunning.

It is a Python 3.8 / Flask 1.1 / SQLAlchemy 1.3 application with Alembic
migrations, Celery workers and a PostgreSQL database.

## Features

* **Catalog** – products and recurring prices (per-unit or package pricing,
  day/week/month/year intervals).
* **Subscriptions** – trials, quantity and price changes with second-precise
  prorations, cancellation now or at period end, automatic renewals.
* **Invoices** – draft → open → paid/void/uncollectible state machine,
  per-customer invoice numbering, one-off invoice items.
* **Discounts** – percent or fixed-amount coupons (`once`, `repeating`,
  `forever`) allocated across invoice lines without losing a cent.
* **Tax** – exclusive/inclusive rates by country and state, EU reverse charge,
  tax-exempt customers, correct rounding for 0-, 2- and 3-decimal currencies.
* **Payments** – pluggable gateway (a deterministic fake gateway ships for
  development), configurable retry schedule and final action.
* **API** – JSON REST API with API-key auth, cursor pagination and uniform
  errors.

## Technology

| component | version |
|---|---|
| Python | 3.8 |
| Flask / Werkzeug | 1.1.2 / 1.0.1 |
| SQLAlchemy / Flask-SQLAlchemy | 1.3.17 / 2.4.3 |
| Alembic / Flask-Migrate | 1.4.2 / 2.5.3 |
| marshmallow | 3.6.1 |
| Celery / Redis client | 4.4.5 / 3.5.3 |
| PostgreSQL (psycopg2) | 12 (2.8.5) |
| pytest / black / flake8 / isort | 5.4.3 / 19.10b0 / 3.8.3 / 4.3.21 |

Every dependency is pinned in `requirements.txt` / `requirements-dev.txt`.

## Getting started

```bash
python3.8 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt

export FLASK_APP=wsgi.py             # Windows: set FLASK_APP=wsgi.py
flask db upgrade                     # creates ledgerline-dev.db (SQLite)
flask tenants create --name "Acme GmbH" --country DE --currency eur
flask run
```

```bash
curl -s localhost:5000/v1/customers \
  -H "Authorization: Bearer sk_test_..." \
  -H "Content-Type: application/json" \
  -d '{"email": "jane@example.com", "address": {"country": "DE"}}'
```

With Docker (PostgreSQL 12 + Redis 6 + web + Celery worker):

```bash
docker-compose up --build web worker
docker-compose run --rm tests        # test suite against PostgreSQL
```

Background jobs (run by Celery beat, or by hand):

```bash
flask billing run                    # renew subscriptions whose period ended
flask billing retry-payments         # dunning retries
```

## Tests

```bash
python -m pytest tests               # SQLite in memory, ~30 s
make lint
TEST_DATABASE_URL=postgresql://... python -m pytest tests
```

The suite is organised as `tests/unit` (pure functions), `tests/integration`
(services against a real database), `tests/api` (HTTP) and
`tests/migrations` (Alembic upgrade/downgrade and model drift).

## Documentation

* [docs/architecture.md](docs/architecture.md) – packages and transactions
* [docs/billing-model.md](docs/billing-model.md) – **the billing specification**
* [docs/api.md](docs/api.md) – API reference
* [docs/adr](docs/adr) – architecture decision records
* [CHANGELOG.md](CHANGELOG.md)

## Repository layout

```
ledgerline/
  api/          Flask blueprint: auth, schemas, pagination, resources
  billing/      periods, pricing, proration, discounts, tax, invoices, subscriptions
  payments/     gateway adapters, collection, dunning
  models/       SQLAlchemy models
  tasks/        Celery app and jobs
migrations/     Alembic revisions
tests/          unit, integration, api and migration tests
docs/           architecture, billing model, API, ADRs
```
