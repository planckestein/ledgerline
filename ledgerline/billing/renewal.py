"""Subscription renewals (the "billing cycle" job)."""
import logging

from ledgerline import clock
from ledgerline.billing import periods
from ledgerline.billing.subscriptions import _cycle_invoice, finalize_and_collect
from ledgerline.events import bus
from ledgerline.extensions import db
from ledgerline.models import InvoiceItem, Subscription
from ledgerline.models.subscription import BILLABLE_STATUSES

log = logging.getLogger(__name__)


def _has_pending_items(subscription):
    return (
        db.session.query(InvoiceItem.id)
        .filter(
            InvoiceItem.subscription_id == subscription.id,
            InvoiceItem.invoice_id.is_(None),
        )
        .first()
        is not None
    )


def _end_subscription(subscription, now):
    """Handle ``cancel_at_period_end`` once the period is over."""
    period = (subscription.current_period_start, subscription.current_period_end)
    was_trialing = subscription.status == "trialing"
    has_metered = any(item.price.is_metered for item in subscription.active_items)

    invoice = None
    if (has_metered and not was_trialing) or _has_pending_items(subscription):
        invoice = _cycle_invoice(
            subscription,
            "subscription_cancel",
            metered_period=None if was_trialing else period,
        )
        finalize_and_collect(invoice)

    subscription.status = "canceled"
    subscription.canceled_at = subscription.canceled_at or now
    subscription.ended_at = subscription.current_period_end
    bus.publish("customer.subscription.deleted", subscription)
    return invoice


def _renew_once(subscription, now):
    if subscription.cancel_at_period_end:
        return _end_subscription(subscription, now)

    was_trialing = subscription.status == "trialing"
    ended_period = (subscription.current_period_start, subscription.current_period_end)
    price = subscription.primary_price
    new_start, new_end = periods.next_period(
        subscription.current_period_end, price.interval, price.interval_count
    )
    subscription.current_period_start = new_start
    subscription.current_period_end = new_end
    if was_trialing:
        subscription.status = "active"

    invoice = _cycle_invoice(
        subscription,
        "subscription_cycle",
        licensed_period=(new_start, new_end),
        metered_period=None if was_trialing else ended_period,
    )
    finalize_and_collect(invoice)
    bus.publish("customer.subscription.updated", subscription)
    return invoice


def renew_subscription(subscription, now=None):
    """Renew ``subscription`` for every period that has ended by ``now``.

    Returns the invoices that were created. Several periods are billed at once
    if the job has not run for a while.
    """
    now = now or clock.utcnow()
    invoices = []
    while subscription.status in BILLABLE_STATUSES and subscription.current_period_end <= now:
        invoice = _renew_once(subscription, now)
        if invoice is not None:
            invoices.append(invoice)
    return invoices


def due_subscription_ids(now):
    rows = (
        db.session.query(Subscription.id)
        .filter(
            Subscription.status.in_(BILLABLE_STATUSES),
            Subscription.current_period_end <= now,
        )
        .order_by(Subscription.id)
        .all()
    )
    return [row.id for row in rows]


def run_billing_cycle(now=None):
    """Renew every due subscription, committing one subscription at a time."""
    now = now or clock.utcnow()
    summary = {"subscriptions": 0, "invoices": 0, "errors": []}
    for subscription_id in due_subscription_ids(now):
        subscription = Subscription.query.get(subscription_id)
        try:
            invoices = renew_subscription(subscription, now)
            db.session.commit()
        except Exception:
            db.session.rollback()
            log.exception("Renewal failed for subscription id=%s", subscription_id)
            summary["errors"].append(subscription_id)
            continue
        summary["subscriptions"] += 1
        summary["invoices"] += len(invoices)
    return summary
