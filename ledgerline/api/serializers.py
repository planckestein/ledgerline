"""Public JSON representations of domain objects.

Changing a representation is an API change. Timestamps are Unix seconds;
money is in minor units.
"""
import calendar


def ts(moment):
    if moment is None:
        return None
    return calendar.timegm(moment.utctimetuple())


def serialize_customer(customer):
    default = customer.default_payment_method
    return {
        "id": customer.public_id,
        "object": "customer",
        "email": customer.email,
        "name": customer.name,
        "currency": customer.currency,
        "address": customer.address,
        "invoice_prefix": customer.invoice_prefix,
        "default_payment_method": default.public_id if default else None,
        "metadata": customer.metadata_ or {},
        "created": ts(customer.created_at),
    }


def serialize_payment_method(method):
    return {
        "id": method.public_id,
        "object": "payment_method",
        "type": method.type,
        "card": {"brand": method.card_brand, "last4": method.card_last4},
        "customer": method.customer.public_id,
        "is_default": method.is_default,
        "created": ts(method.created_at),
    }


def serialize_product(product):
    return {
        "id": product.public_id,
        "object": "product",
        "name": product.name,
        "description": product.description,
        "active": product.active,
        "created": ts(product.created_at),
    }


def serialize_price(price):
    return {
        "id": price.public_id,
        "object": "price",
        "product": price.product.public_id,
        "nickname": price.nickname,
        "currency": price.currency,
        "unit_amount": price.unit_amount,
        "billing_scheme": price.billing_scheme,
        "package_size": price.package_size,
        "recurring": {
            "interval": price.interval,
            "interval_count": price.interval_count,
        },
        "active": price.active,
        "created": ts(price.created_at),
    }


def serialize_subscription_item(item):
    return {
        "id": item.public_id,
        "object": "subscription_item",
        "price": item.price.public_id,
        "quantity": item.quantity,
        "created": ts(item.created_at),
    }


def serialize_subscription(subscription):
    return {
        "id": subscription.public_id,
        "object": "subscription",
        "customer": subscription.customer.public_id,
        "status": subscription.status,
        "collection_method": subscription.collection_method,
        "days_until_due": subscription.days_until_due,
        "billing_cycle_anchor": ts(subscription.billing_cycle_anchor),
        "current_period_start": ts(subscription.current_period_start),
        "current_period_end": ts(subscription.current_period_end),
        "trial_start": ts(subscription.trial_start),
        "trial_end": ts(subscription.trial_end),
        "cancel_at_period_end": subscription.cancel_at_period_end,
        "canceled_at": ts(subscription.canceled_at),
        "ended_at": ts(subscription.ended_at),
        "items": {
            "object": "list",
            "data": [serialize_subscription_item(item) for item in subscription.active_items],
        },
        "created": ts(subscription.created_at),
    }


def serialize_invoice_line(line):
    return {
        "id": line.public_id,
        "object": "line_item",
        "type": line.line_type,
        "description": line.description,
        "quantity": line.quantity,
        "amount": line.amount,
        "price": line.price.public_id if line.price is not None else None,
        "proration": line.proration,
        "period": {"start": ts(line.period_start), "end": ts(line.period_end)},
    }


def serialize_invoice(invoice):
    return {
        "id": invoice.public_id,
        "object": "invoice",
        "number": invoice.number,
        "customer": invoice.customer.public_id,
        "subscription": invoice.subscription.public_id if invoice.subscription else None,
        "status": invoice.status,
        "billing_reason": invoice.billing_reason,
        "collection_method": invoice.collection_method,
        "currency": invoice.currency,
        "period_start": ts(invoice.period_start),
        "period_end": ts(invoice.period_end),
        "subtotal": invoice.subtotal,
        "total": invoice.total,
        "amount_due": invoice.amount_due,
        "amount_paid": invoice.amount_paid,
        "attempt_count": invoice.attempt_count,
        "next_payment_attempt": ts(invoice.next_payment_attempt),
        "due_date": ts(invoice.due_date),
        "lines": {
            "object": "list",
            "data": [serialize_invoice_line(line) for line in invoice.lines],
        },
        "created": ts(invoice.created_at),
        "finalized_at": ts(invoice.finalized_at),
        "paid_at": ts(invoice.paid_at),
    }


def serialize_invoice_item(item):
    return {
        "id": item.public_id,
        "object": "invoiceitem",
        "customer": item.customer.public_id,
        "subscription": item.subscription.public_id if item.subscription else None,
        "invoice": item.invoice.public_id if item.invoice else None,
        "description": item.description,
        "quantity": item.quantity,
        "amount": item.amount,
        "currency": item.currency,
        "proration": item.proration,
        "period": {"start": ts(item.period_start), "end": ts(item.period_end)},
        "created": ts(item.created_at),
    }


def serialize_payment_attempt(attempt):
    return {
        "id": attempt.public_id,
        "object": "payment_attempt",
        "invoice": attempt.invoice.public_id,
        "amount": attempt.amount,
        "currency": attempt.currency,
        "status": attempt.status,
        "failure_code": attempt.failure_code,
        "failure_message": attempt.failure_message,
        "created": ts(attempt.created_at),
    }
