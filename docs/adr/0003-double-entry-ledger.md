# ADR 0003: Double-entry ledger as the financial source of truth

**Status:** accepted

## Context

Finance reconciles our numbers against the payment processor every month.
Deriving balances from invoice rows was ambiguous (voids, write-offs,
partial states) and impossible to audit.

## Decision

* Every money-moving transition posts a balanced `JournalEntry` in the same
  transaction (`ledgerline.ledger.posting`).
* Accounts: `1000_cash`, `1100_accounts_receivable`, `2100_tax_payable`,
  `2200_customer_credit` (reserved), `4000_revenue`, `6100_bad_debt_expense`.
* Receivable lines carry `customer_id` so a per-customer sub-ledger can be
  reported.
* `post_entry` refuses unbalanced entries with `LedgerImbalanceError`. This is
  deliberately loud: an imbalance means an invoice's totals disagree with its
  lines, and we would rather fail the finalization than book wrong numbers.

## Consequences

* `GET /v1/ledger/trial_balance` must always report `balanced: true`.
* Any new money flow (refunds, credit balances, ...) needs a posting rule and
  a test that the trial balance still balances.
