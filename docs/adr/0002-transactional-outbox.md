# ADR 0002: Transactional outbox for events and webhooks

**Status:** accepted

## Context

Merchants rely on webhooks (`invoice.paid`, `customer.subscription.deleted`)
to provision and de-provision access. Sending HTTP requests from inside a
request handler loses events when the transaction rolls back after the send,
and sends events for changes that never committed.

## Decision

* `events.bus.publish()` writes the `Event` row and its `WebhookDelivery`
  rows in the **same transaction** as the business change.
* A separate job (`ledgerline.dispatch_webhooks`, every 15 s) delivers due
  deliveries and commits after each one.
* Payloads are snapshots taken at publish time.
* Deliveries are signed: `Ledgerline-Signature: t=<unix>,v1=<hmac-sha256>`.
* Failed deliveries back off exponentially (1, 2, 4 ... minutes, capped at 6
  hours) and are abandoned after `LEDGERLINE_WEBHOOK_MAX_ATTEMPTS`.

## Consequences

* Delivery is at-least-once; receivers must de-duplicate by event id.
* Webhooks lag the business change by up to one dispatcher interval.
