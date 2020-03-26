# Contributing

## Workflow

1. Branch from `main`; keep pull requests focused.
2. `make format lint test` must pass locally. CI runs the suite against both
   SQLite and PostgreSQL 12.
3. Every behaviour change comes with tests. Money logic changes must also
   update [docs/billing-model.md](docs/billing-model.md).
4. Schema changes need an Alembic revision (`flask db migrate -m "..."`,
   then review and edit it by hand):
   * use `op.batch_alter_table` so it runs on SQLite;
   * name every constraint (see `NAMING_CONVENTION`);
   * write a working `downgrade()`, including data;
   * `tests/migrations` must stay green (no model/migration drift).
5. Update `CHANGELOG.md` under an "Unreleased" heading.

## Conventions

* Services `flush()`, API views and jobs `commit()`.
* Read the time from `ledgerline.clock.utcnow()`, never `datetime.utcnow()`.
* Amounts are `int` minor units; use `ledgerline.money.Money` for arithmetic.
* Raise subclasses of `ledgerline.errors.LedgerlineError` for client errors.
* Public ids (`cus_...`) are the only identifiers exposed by the API.
