# Ledgerline

Ledgerline is a multi-tenant **subscription billing service**: merchants
(tenants) define products and recurring prices, subscribe their customers, and
Ledgerline takes care of billing periods, prorations, invoices and card
payments with dunning.

It is a Python 3.8 / Flask 1.1 / SQLAlchemy 1.3 application with Alembic
migrations, Celery workers and a PostgreSQL database.

## Features

* **Catalog** – products and recurring prices (per-unit or package pricing,
  day/week/month/year intervals).
* **Subscriptions** – trials, quantity and price changes with second-precise
  prorations, cancellation now or at period end, automatic renewals.
* **Invoices** – draft → open → paid/void/uncollectible state machine,
  per-customer invoice numbering, one-off invoice items.
* **Payments** – pluggable gateway (a deterministic fake gateway ships for
  development), configurable retry schedule and final action.
* **API** – JSON REST API with API-key auth, cursor pagination and uniform
  errors.

## Technology

| component | version |
|---|---|
| Python | 3.8 |
| Flask / Werkzeug | 1.1.1 / 0.16.0 |
| SQLAlchemy / Flask-SQLAlchemy | 1.3.12 / 2.4.1 |
| Alembic / Flask-Migrate | 1.3.2 / 2.5.2 |
| marshmallow | 3.3.0 |
| Celery / Redis client | 4.4.0 / 3.3.11 |
| PostgreSQL (psycopg2) | 12 (2.8.4) |
| pytest / black / flake8 / isort | 5.3.2 / 19.10b0 / 3.7.9 / 4.3.21 |

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

With Docker (PostgreSQL 12 + Redis 5 + web + Celery worker):

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

## Repository layout

```
ledgerline/
  api/          Flask blueprint: auth, schemas, pagination, resources
  billing/      periods, pricing, proration, invoices, subscriptions
  payments/     gateway adapters, collection, dunning
  models/       SQLAlchemy models
  tasks/        Celery app and jobs
migrations/     Alembic revisions
tests/          unit, integration, api and migration tests
docs/           architecture, billing model, API, ADRs
```
