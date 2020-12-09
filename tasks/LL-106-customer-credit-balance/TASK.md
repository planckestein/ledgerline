# LL-106: Feature: customer credit balance

| | |
|---|---|
| **Type** | Feature + database migration (cross-cutting) |
| **Difficulty** | Very hard |
| **Areas** | invoicing, ledger, payments, subscriptions, API, Alembic |
| **Verify** | `python scripts/verify_task.py LL-106` |

## Motivation

Today a downgrade billed with `proration_behavior="always_invoice"` fails
with `invoice_negative_total`, and cancelling with `prorate` + `invoice_now`
silently leaves the credit as pending invoice items. Support also has no way
to grant goodwill credit. Merchants want a **customer balance**: credits are
stored on the customer and consumed automatically by later invoices.

## Specification

### Concepts

* Every customer has a `balance` in minor units of the customer's currency.
  **Negative means credit** the merchant owes the customer (the convention of
  major payment processors). It starts at 0 and, with this feature, can only
  become negative or return towards 0.
* Every change of the balance is recorded as a **customer balance
  transaction** with a signed `amount` (negative = the customer gains credit)
  and the resulting `ending_balance`. Types:

  | type | when | amount |
  |---|---|---|
  | `adjustment` | support grants credit through the API | negative |
  | `invoice_credit` | an invoice with a negative total is finalized | the (negative) total |
  | `applied_to_invoice` | credit is consumed by a positive invoice | + amount applied |
  | `invoice_void` | an open invoice that consumed credit is voided | − amount applied |

### Invoices

When an invoice is finalized:

* `starting_balance` = the customer's balance before finalization and
  `ending_balance` = the balance after it (both are set on every finalized
  invoice, also when the balance is 0).
* **total > 0 and credit available**: `applied = min(total, -balance)` is
  consumed; `amount_due = total - applied`. If `amount_due == 0` the invoice
  is `paid` immediately, without a charge or payment attempt.
  `amount_paid` only reflects money collected by the payment gateway.
* **total < 0**: finalization no longer fails. The invoice becomes `paid` with
  `amount_due = 0` and its total is credited to the balance.
* Automatic collection, retries and the `pay` endpoint always charge
  `amount_due`.
* Voiding an open invoice that consumed credit gives the consumed credit back.

As a consequence, `cancel_subscription(prorate=True, invoice_now=True)`
finalizes a negative final invoice into a credit instead of leaving pending
items, and `create_manual_invoice` + `finalize_invoice` accept negative
totals. **This intentionally changes the behaviour covered by two existing
tests** (`test_negative_total_cannot_be_finalized` and
`test_negative_final_invoice_keeps_credit_pending`); update them to assert
the new behaviour.

### Ledger

Use account `2200_customer_credit` (liability) and add `4900_credit_adjustments`
(contra-revenue, type `revenue`):

| event | debit | credit |
|---|---|---|
| adjustment | `4900_credit_adjustments` | `2200_customer_credit` |
| negative invoice credited | `1100_accounts_receivable` | `2200_customer_credit` |
| credit applied to an invoice | `2200_customer_credit` | `1100_accounts_receivable` |
| applied credit restored on void | `1100_accounts_receivable` | `2200_customer_credit` |

Invariants: the trial balance always balances; for every currency, the
balance of `2200_customer_credit` (debits − credits) equals the sum of the
balances of the customers billed in that currency; receivables of a customer
equal the `amount_due` of their open invoices.

### API

* Customer objects gain `balance`.
* Invoice objects gain `starting_balance` and `ending_balance` (`null` for
  drafts).
* `POST /v1/customers/:id/balance_transactions` with
  `{"amount": -500, "currency": "eur", "description": "Goodwill"}` creates an
  `adjustment`. `amount` must be a negative integer (400, `param: amount`);
  `currency` must match the customer's currency (400, `param: currency`);
  a customer without a currency adopts it.
* `GET /v1/customers/:id/balance_transactions` lists transactions newest
  first using the standard list envelope and pagination parameters.
* Transaction objects: `id` (prefix `cbtxn_`), `object`
  (`"customer_balance_transaction"`), `customer`, `type`, `amount`, `currency`,
  `invoice` (id or `null`), `description`, `ending_balance`, `created`.

### Storage

`customers.balance` (integer, not null, default 0),
`invoices.starting_balance` / `invoices.ending_balance` (nullable integers) and
a `customer_balance_transactions` table, shipped as an Alembic migration with
a working downgrade. Existing customers start with a balance of 0.

## Acceptance criteria

1. All tests in `tasks/LL-106-customer-credit-balance/tests/` pass.
2. The full regression suite passes (with the two tests above updated).
3. `docs/billing-model.md` (ledger table, invoice rules), `docs/api.md` and
   `CHANGELOG.md` describe the feature.
4. No other existing test is deleted or weakened; `make lint` passes.
