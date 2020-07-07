"""Subscription lifecycle: create, change items, cancel.

Renewals live in :mod:`ledgerline.billing.renewal`.
"""
from datetime import timedelta

from ledgerline import clock
from ledgerline.billing import discounts, invoice_builder, invoicing, periods, pricing, proration
from ledgerline.errors import InvalidRequestError, InvalidStateTransition
from ledgerline.extensions import db
from ledgerline.models import InvoiceItem, Subscription, SubscriptionItem

COLLECTION_METHODS = ("charge_automatically", "send_invoice")
PRORATION_BEHAVIORS = ("create_prorations", "none", "always_invoice")
DEFAULT_DAYS_UNTIL_DUE = 30


def _validate_items(customer, items, expected_currency=None, expected_interval=None):
    """Validate ``[(price, quantity), ...]`` and return it with metered quantities normalized."""
    if not items:
        raise InvalidRequestError("A subscription needs at least one item", param="items")
    seen = set()
    normalized = []
    currency = expected_currency
    interval = expected_interval
    for price, quantity in items:
        if price.tenant_id != customer.tenant_id:
            raise InvalidRequestError("No such price: %s" % price.public_id, param="items")
        if not price.active:
            raise InvalidRequestError("Price %s is not active" % price.public_id, param="items")
        if price.id in seen:
            raise InvalidRequestError(
                "Price %s appears more than once" % price.public_id, param="items"
            )
        seen.add(price.id)
        if currency is None:
            currency = price.currency
        elif price.currency != currency:
            raise InvalidRequestError(
                "All items must use the same currency (%s)" % currency, param="items"
            )
        if interval is None:
            interval = (price.interval, price.interval_count)
        elif (price.interval, price.interval_count) != interval:
            raise InvalidRequestError("All items must use the same billing interval", param="items")
        if price.is_metered:
            quantity = 1
        elif quantity is None or quantity < 1:
            raise InvalidRequestError("quantity must be at least 1", param="items")
        normalized.append((price, quantity))

    if customer.currency is not None and customer.currency != currency:
        raise InvalidRequestError(
            "Customer %s is billed in %s, not %s"
            % (customer.public_id, customer.currency, currency),
            param="items",
        )
    return normalized


def _cycle_invoice(subscription, billing_reason, licensed_period=None, metered_period=None):
    period = licensed_period or metered_period
    invoice = invoice_builder.create_draft(
        subscription.customer,
        currency=subscription.currency,
        billing_reason=billing_reason,
        subscription=subscription,
        collection_method=subscription.collection_method,
        days_until_due=subscription.days_until_due,
        period_start=period[0] if period else None,
        period_end=period[1] if period else None,
    )
    if licensed_period:
        invoice_builder.add_licensed_lines(invoice, subscription, *licensed_period)
    if metered_period:
        invoice_builder.add_metered_lines(invoice, subscription, *metered_period)
    invoice_builder.attach_pending_items(invoice)
    return invoice


def finalize_and_collect(invoice):
    """Finalize ``invoice`` and, for automatic collection, try to charge it once."""
    from ledgerline.payments import service as payment_service

    invoicing.finalize_invoice(invoice)
    if invoice.status == "open" and invoice.collection_method == "charge_automatically":
        payment_service.collect_invoice(invoice)
    return invoice


def create_subscription(
    customer,
    items,
    trial_period_days=None,
    coupon=None,
    collection_method="charge_automatically",
    days_until_due=None,
):
    if collection_method not in COLLECTION_METHODS:
        raise InvalidRequestError("Unknown collection_method", param="collection_method")
    if collection_method == "charge_automatically" and customer.default_payment_method is None:
        raise InvalidRequestError(
            "Customer %s has no default payment method" % customer.public_id,
            param="customer",
            code="missing_payment_method",
        )
    if collection_method == "send_invoice" and days_until_due is None:
        days_until_due = DEFAULT_DAYS_UNTIL_DUE

    specs = _validate_items(customer, items)
    first_price = specs[0][0]
    if coupon is not None:
        discounts.assert_redeemable(coupon, first_price.currency)

    now = clock.utcnow()
    if customer.currency is None:
        customer.currency = first_price.currency

    subscription = Subscription(
        tenant_id=customer.tenant_id,
        customer=customer,
        status="incomplete",
        collection_method=collection_method,
        days_until_due=days_until_due,
    )
    if trial_period_days:
        trial_end = now + timedelta(days=trial_period_days)
        subscription.status = "trialing"
        subscription.trial_start = now
        subscription.trial_end = trial_end
        subscription.billing_cycle_anchor = trial_end
        subscription.current_period_start = now
        subscription.current_period_end = trial_end
    else:
        start, end = periods.initial_period(now, first_price.interval, first_price.interval_count)
        subscription.billing_cycle_anchor = now
        subscription.current_period_start = start
        subscription.current_period_end = end
    db.session.add(subscription)

    for price, quantity in specs:
        db.session.add(
            SubscriptionItem(
                tenant_id=customer.tenant_id,
                subscription=subscription,
                price=price,
                quantity=quantity,
            )
        )
    db.session.flush()

    if coupon is not None:
        discounts.create_discount(coupon, customer, subscription=subscription, start=now)

    if subscription.status == "trialing":
        return subscription

    invoice = _cycle_invoice(
        subscription,
        "subscription_create",
        licensed_period=(subscription.current_period_start, subscription.current_period_end),
    )
    finalize_and_collect(invoice)
    if invoice.status == "paid" or collection_method == "send_invoice":
        subscription.status = "active"
    return subscription


def _proration_item(subscription, price, quantity, fraction, credit, at):
    full_amount = pricing.amount_for_quantity(price, quantity)
    amount = proration.prorate(full_amount, fraction)
    if amount == 0:
        return None
    label = "Unused time on" if credit else "Remaining time on"
    item = InvoiceItem(
        tenant_id=subscription.tenant_id,
        customer=subscription.customer,
        subscription=subscription,
        price=price,
        description="%s %s after %s"
        % (label, pricing.describe(price, quantity), at.strftime("%d %b %Y")),
        quantity=quantity,
        amount=-amount if credit else amount,
        currency=price.currency,
        proration=True,
        period_start=at,
        period_end=subscription.current_period_end,
    )
    db.session.add(item)
    return item


def update_subscription_items(subscription, items, proration_behavior="create_prorations"):
    """Replace the subscription's items with ``[(price, quantity), ...]``.

    Prices already on the subscription keep their item (and usage history) and
    only change quantity; missing prices are removed; new prices are added.
    Licensed changes are prorated unless ``proration_behavior="none"``.
    """
    if proration_behavior not in PRORATION_BEHAVIORS:
        raise InvalidRequestError("Unknown proration_behavior", param="proration_behavior")
    if subscription.status in ("canceled", "incomplete"):
        raise InvalidStateTransition("Cannot update a %s subscription" % subscription.status)
    specs = _validate_items(
        subscription.customer,
        items,
        expected_currency=subscription.currency,
        expected_interval=subscription.interval,
    )

    now = clock.utcnow()
    prorate = (
        proration_behavior != "none"
        and subscription.status != "trialing"
        and subscription.current_period_start <= now < subscription.current_period_end
    )
    fraction = proration.unused_fraction(
        subscription.current_period_start, subscription.current_period_end, now
    )

    current = {item.price_id: item for item in subscription.active_items}
    desired = {price.id: (price, quantity) for price, quantity in specs}
    created = []

    for price_id, item in current.items():
        licensed = not item.price.is_metered
        if price_id not in desired:
            if prorate and licensed:
                created.append(
                    _proration_item(subscription, item.price, item.quantity, fraction, True, now)
                )
            item.deleted_at = now
            continue
        _, quantity = desired[price_id]
        if quantity != item.quantity:
            if prorate and licensed:
                created.append(
                    _proration_item(subscription, item.price, item.quantity, fraction, True, now)
                )
                created.append(
                    _proration_item(subscription, item.price, quantity, fraction, False, now)
                )
            item.quantity = quantity

    for price_id, (price, quantity) in desired.items():
        if price_id in current:
            continue
        if prorate and not price.is_metered:
            created.append(_proration_item(subscription, price, quantity, fraction, False, now))
        db.session.add(
            SubscriptionItem(
                tenant_id=subscription.tenant_id,
                subscription=subscription,
                price=price,
                quantity=quantity,
            )
        )

    db.session.flush()
    db.session.expire(subscription, ["items"])
    created = [item for item in created if item is not None]

    if proration_behavior == "always_invoice" and created:
        invoice = invoice_builder.create_draft(
            subscription.customer,
            currency=subscription.currency,
            billing_reason="subscription_update",
            subscription=subscription,
            collection_method=subscription.collection_method,
            days_until_due=subscription.days_until_due,
            period_start=now,
            period_end=subscription.current_period_end,
        )
        invoice_builder.attach_pending_items(invoice)
        finalize_and_collect(invoice)
    return subscription


def schedule_cancellation(subscription, cancel_at_period_end=True):
    if subscription.status == "canceled":
        raise InvalidStateTransition("Subscription is already canceled")
    subscription.cancel_at_period_end = cancel_at_period_end
    return subscription


def cancel_subscription(subscription, prorate=False, invoice_now=False):
    """Cancel immediately.

    ``prorate`` credits unused licensed time as pending invoice items.
    ``invoice_now`` bills outstanding metered usage and pending items right
    away; if that invoice would be negative the credits stay pending.
    """
    if subscription.status == "canceled":
        raise InvalidStateTransition("Subscription is already canceled")
    now = clock.utcnow()
    if prorate and subscription.status != "trialing":
        fraction = proration.unused_fraction(
            subscription.current_period_start, subscription.current_period_end, now
        )
        for item in subscription.active_items:
            if not item.price.is_metered:
                _proration_item(subscription, item.price, item.quantity, fraction, True, now)
        db.session.flush()

    if invoice_now:
        metered = None
        if subscription.status != "trialing":
            metered = (subscription.current_period_start, now)
        invoice = _cycle_invoice(subscription, "subscription_cancel", metered_period=metered)
        if invoice.lines:
            invoice_builder.compute_totals(invoice)
        if not invoice.lines or invoice.total < 0:
            invoice_builder.discard_draft(invoice)
        else:
            finalize_and_collect(invoice)

    subscription.status = "canceled"
    subscription.canceled_at = now
    subscription.ended_at = now
    return subscription
