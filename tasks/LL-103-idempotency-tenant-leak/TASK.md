# LL-103: Regression: idempotent requests leak across tenants

| | |
|---|---|
| **Type** | Regression + database migration (security) |
| **Difficulty** | Hard |
| **Areas** | API idempotency, models, Alembic, git history |
| **Verify** | `python scripts/verify_task.py LL-103` |

## Report

> **From:** Security team · **Severity:** critical
>
> Two unrelated merchants integrate through the same e-commerce plugin. The
> plugin derives `Idempotency-Key` from the shop's order number, so both
> merchants send keys like `order-1001`.
>
> * Merchant B created a customer with `Idempotency-Key: order-1001` and got
>   back **merchant A's customer** (`Idempotent-Replayed: true`). Merchant B
>   can now read data belonging to merchant A.
> * Other requests from merchant B fail with `422 idempotency_error`
>   ("Keys for idempotent requests can only be used with the same
>   parameters…") although merchant B never used that key before.
>
> Everything worked on **v1.3.0**; the first reports came in after
> **v1.4.0** was deployed. v1.4.1 is affected as well.

## What we need

1. Find the change that introduced the regression (the repository history
   and tags `v1.3.0`, `v1.4.0`, `v1.4.1` are available; `git bisect` is your
   friend).
2. Fix it **without** throwing away the performance work of that release:
   idempotency keys must still be looked up through `key_hash`.
3. Idempotency keys are scoped per tenant (docs/billing-model.md §8): the same
   key used by two tenants refers to two independent requests. This must also
   be enforced by the database, so ship an **Alembic migration** that
   replaces the global uniqueness on `key_hash` with uniqueness on
   `(tenant_id, key_hash)`. The migration must
   * keep existing rows,
   * run on SQLite and PostgreSQL,
   * have a working `downgrade()`,
   * leave the database identical to the models (`tests/migrations` stays
     green).
4. Add an entry to `CHANGELOG.md` under a new `## Unreleased` heading.

Behaviour within a single tenant (replays, 422 on parameter mismatch, 409 for
in-flight keys, expiry) must not change.

## Acceptance criteria

1. All tests in `tasks/LL-103-idempotency-tenant-leak/tests/` pass.
2. The full regression suite (`python -m pytest tests`) passes.
3. Exactly one new migration head; `flask db upgrade` from v1.4.1 works.
4. No existing test is deleted or weakened; `make lint` passes.
