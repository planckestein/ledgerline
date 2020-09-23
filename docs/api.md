# API reference (v1)

Base URL: `/v1`. Authenticate with `Authorization: Bearer <secret key>`.
Request bodies are JSON objects; unknown parameters are rejected. Timestamps
are Unix seconds, amounts are integers in minor units, currencies are
lower-case ISO 4217 codes.

## Errors

```json
{"error": {"type": "invalid_request_error", "code": "resource_missing",
           "message": "No such customer: 'cus_123'", "param": "id"}}
```

| HTTP | type | when |
|---|---|---|
| 400 | `invalid_request_error` | validation failed (`param` names the field) |
| 401 | `authentication_error` | missing, invalid or revoked key |
| 402 | `card_error` | the charge was declined (`code` from the gateway) |
| 404 | `invalid_request_error` | object does not exist for this tenant |
| 409 | `invalid_request_error` | illegal state transition |

## Pagination

`GET` list endpoints accept `limit` (1-100, default 10), `starting_after` and
`ending_before` and return `{"object": "list", "data": [...], "has_more": bool}`.

## Resources

| method & path | description |
|---|---|
| `POST /customers`, `GET /customers`, `GET/POST /customers/:id` | customers (`email`, `name`, `address`, `vat_id`, `tax_exempt`, `metadata`) |
| `POST/GET /customers/:id/payment_methods` | attach a card token (`tok_visa`, ...) |
| `POST /customers/:id/discount` | apply a coupon to every invoice of the customer |
| `POST/GET /products`, `GET/POST /products/:id` | products |
| `POST/GET /prices`, `GET/POST /prices/:id` | recurring prices (`unit_amount`, `billing_scheme`, `recurring`) |
| `POST/GET /tax_rates`, `GET/POST /tax_rates/:id` | tax rates |
| `POST/GET /coupons`, `GET /coupons/:id` | coupons |
| `POST/GET /subscriptions`, `GET/POST /subscriptions/:id` | subscriptions; update `items`, `proration_behavior`, `cancel_at_period_end` |
| `POST /subscriptions/:id/cancel` | cancel now (`prorate`, `invoice_now`) |
| `POST /subscription_items/:id/usage_records` | report metered usage |
| `GET /subscription_items/:id/usage_summary` | usage in the current period |
| `POST/GET /invoiceitems` | one-off charges and credits |
| `POST /invoices`, `GET /invoices`, `GET /invoices/:id` | manual draft invoices, listing |
| `POST /invoices/:id/finalize` \| `pay` \| `void` \| `mark_uncollectible` | invoice lifecycle |
| `GET /invoices/:id/payment_attempts` | charge attempts |
| `POST/GET /webhook_endpoints`, `GET/POST /webhook_endpoints/:id` | webhook endpoints |
| `GET /events`, `GET /events/:id` | the event log |
| `GET /ledger/trial_balance?currency=eur` | ledger trial balance |
