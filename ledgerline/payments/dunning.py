"""Dunning: what happens after a failed payment.

The tenant's ``dunning_retry_days`` (e.g. ``"3,5,7"``) lists the number of
days to wait before each retry, counted from the previous attempt. When the
last retry fails, ``dunning_final_action`` decides the subscription's fate:

* ``cancel``: the subscription is canceled and the invoice marked uncollectible;
* ``mark_unpaid``: the subscription becomes ``unpaid`` and the invoice stays open.

The first invoice of a subscription is never retried; the subscription stays
``incomplete`` until that invoice is paid.
"""
import logging
from datetime import timedelta

from ledgerline import clock
from ledgerline.events import bus
from ledgerline.extensions import db
from ledgerline.models import Invoice

log = logging.getLogger(__name__)

MAX_RETRIES = 8


def parse_retry_schedule(spec):
    """``"3,5,7"`` -> ``[3, 5, 7]``. Raises ``ValueError`` for malformed schedules."""
    if spec is None:
        return []
    days = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        value = int(part)
        if value < 1 or value > 30:
            raise ValueError("retry delays must be between 1 and 30 days")
        days.append(value)
    if len(days) > MAX_RETRIES:
        raise ValueError("at most %d retries are allowed" % MAX_RETRIES)
    return days


def handle_payment_failure(invoice, attempt, now):
    from ledgerline.billing import invoicing

    subscription = invoice.subscription
    bus.publish("invoice.payment_failed", invoice)

    if invoice.billing_reason == "subscription_create" and subscription is not None:
        subscription.status = "incomplete"
        invoice.next_payment_attempt = None
        return
    if invoice.collection_method != "charge_automatically":
        return

    tenant = invoice.customer.tenant
    schedule = parse_retry_schedule(tenant.dunning_retry_days)
    retries_used = invoice.attempt_count - 1
    if retries_used < len(schedule):
        invoice.next_payment_attempt = now + timedelta(days=schedule[retries_used])
        if subscription is not None and subscription.status in ("active", "trialing"):
            subscription.status = "past_due"
            bus.publish("customer.subscription.updated", subscription)
        return

    invoice.next_payment_attempt = None
    if subscription is None:
        return
    if tenant.dunning_final_action == "mark_unpaid":
        subscription.status = "unpaid"
        bus.publish("customer.subscription.updated", subscription)
    else:
        subscription.status = "canceled"
        subscription.canceled_at = now
        subscription.ended_at = now
        invoicing.mark_uncollectible(invoice)
        bus.publish("customer.subscription.deleted", subscription)


def due_invoice_ids(now):
    rows = (
        db.session.query(Invoice.id)
        .filter(
            Invoice.status == "open",
            Invoice.collection_method == "charge_automatically",
            Invoice.next_payment_attempt.isnot(None),
            Invoice.next_payment_attempt <= now,
        )
        .order_by(Invoice.next_payment_attempt, Invoice.id)
        .all()
    )
    return [row.id for row in rows]


def retry_due_payments(now=None):
    from ledgerline.payments import service

    now = now or clock.utcnow()
    summary = {"attempted": 0, "succeeded": 0, "failed": 0, "errors": []}
    for invoice_id in due_invoice_ids(now):
        invoice = Invoice.query.get(invoice_id)
        try:
            attempt = service.collect_invoice(invoice)
            db.session.commit()
        except Exception:
            db.session.rollback()
            log.exception("Payment retry failed for invoice id=%s", invoice_id)
            summary["errors"].append(invoice_id)
            continue
        summary["attempted"] += 1
        summary["succeeded" if attempt.status == "succeeded" else "failed"] += 1
    return summary
