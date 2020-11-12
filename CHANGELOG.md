# Changelog

All notable changes to this project are documented here. The project follows
semantic versioning.

## Unreleased

### Added
- `POST /v1/customers/import` creates up to 500 customers in one request.
- `flask ledger trial-balance <tenant>` prints the trial balance for finance.

## 1.3.0

### Added
- Idempotency keys for every `POST` endpoint (`Idempotency-Key` header).
- Transactional outbox, webhook endpoints and signed webhook delivery.
- Double-entry ledger and `GET /v1/ledger/trial_balance`.

## 1.2.0

### Added
- Tax rates (exclusive and inclusive), EU reverse charge, tax-exempt customers.
- Metered prices and usage records (`sum`, `max`, `last_during_period`).

## 1.1.0

### Added
- Coupons and discounts (`once`, `repeating`, `forever`; percent or amount off).

## 1.0.0

- Initial release: tenants, API keys, customers, products, prices,
  subscriptions, invoices, payments with dunning.
