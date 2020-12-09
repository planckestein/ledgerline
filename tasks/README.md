# Long-horizon coding assessment

This directory contains seven self-contained engineering tasks set in the
Ledgerline code base. Each task starts from the same commit (tag
`assessment-base`) and resembles real tickets: a symptom or a product
requirement, a pointer to the specification, and verifiable acceptance
criteria. None of them can be solved by editing a single function: you will
have to read the specification in `docs/`, trace behaviour across the
billing, ledger, payments and API layers, use the git history, write
migrations, and keep a 280-test regression suite green.

| task | type | difficulty | what it exercises |
|---|---|---|---|
| [LL-101](LL-101-billing-anchor-drift/TASK.md) | bug fix | hard | date arithmetic, renewal job, trials, prorations |
| [LL-102](LL-102-discount-tax-rounding/TASK.md) | bug fix | medium–hard | money allocation, currency exponents, ledger invariants |
| [LL-103](LL-103-idempotency-tenant-leak/TASK.md) | regression + migration | hard | `git bisect`, multi-tenant security, Alembic constraint changes |
| [LL-104](LL-104-pagination-and-n-plus-one/TASK.md) | bug fix + performance | medium–hard | keyset pagination, SQLAlchemy loader strategies |
| [LL-105](LL-105-tiered-pricing/TASK.md) | feature + migration | hard | domain modelling, validation, pricing, prorations |
| [LL-106](LL-106-customer-credit-balance/TASK.md) | feature + migration | very hard | cross-cutting change: invoices, ledger, payments, API |
| [LL-107](LL-107-structured-billing-addresses/TASK.md) | data migration | very hard | schema + data migration with legacy formats, refactoring |

Tasks are independent: solve each one on its own branch from
`assessment-base`.

## Ground rules

* Read `docs/billing-model.md` first — it is the specification. When the
  code and the specification disagree, the specification wins.
* Do **not** modify anything under `tasks/<task>/tests` or
  `tasks/<task>/fixtures`; the verifier checks their SHA-256.
* Do not delete or weaken existing tests. Where a task explicitly changes
  existing behaviour it says so; update those tests to assert the new
  behaviour.
* Stay within the pinned 2020 toolchain (Python 3.8, Flask 1.1,
  SQLAlchemy 1.3, Alembic 1.4, marshmallow 3.8, pytest 6.1). No new
  dependencies.
* Schema changes go through Alembic revisions that run on SQLite and
  PostgreSQL, name their constraints and implement `downgrade()`.
* Keep the code idiomatic for this repository (see `CONTRIBUTING.md`).

## Verifying a solution

```bash
python scripts/verify_task.py --list
python scripts/verify_task.py LL-104 --quick   # acceptance tests only, fast feedback
python scripts/verify_task.py LL-104           # integrity + acceptance + regression + lint
python scripts/verify_task.py LL-104 --json    # machine-readable report
```

A task is **accepted** when the verifier prints `RESULT: PASSED`.

## Grading rubric (suggested)

| weight | criterion |
|---|---|
| 40 % | acceptance tests pass |
| 25 % | regression suite and lint pass; no weakened tests |
| 20 % | code review: root cause fixed (not symptoms), consistent with the architecture, no duplicated logic, migrations safe for production data |
| 15 % | engineering hygiene: focused commits, clear messages, tests added for the fix, docs/CHANGELOG updated where required |

Reference solutions are intentionally not part of this repository.
