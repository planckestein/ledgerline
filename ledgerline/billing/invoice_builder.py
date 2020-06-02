"""Assemble draft invoices and compute their totals."""
from sqlalchemy import or_

from ledgerline.billing import discounts, pricing
from ledgerline.billing import tax as taxes
from ledgerline.billing.periods import describe as describe_period
from ledgerline.extensions import db
from ledgerline.models import Invoice, InvoiceItem, InvoiceLine


def create_draft(
    customer,
    *,
    currency,
    billing_reason,
    subscription=None,
    collection_method="charge_automatically",
    days_until_due=None,
    period_start=None,
    period_end=None,
):
    invoice = Invoice(
        tenant_id=customer.tenant_id,
        customer=customer,
        subscription=subscription,
        status="draft",
        currency=currency,
        billing_reason=billing_reason,
        collection_method=collection_method,
        days_until_due=days_until_due,
        period_start=period_start,
        period_end=period_end,
    )
    db.session.add(invoice)
    return invoice


def _append_line(invoice, **fields):
    line = InvoiceLine(position=len(invoice.lines), **fields)
    invoice.lines.append(line)
    return line


def add_licensed_lines(invoice, subscription, period_start, period_end):
    """Charge licensed items in advance for ``[period_start, period_end)``."""
    for item in subscription.active_items:
        _append_line(
            invoice,
            line_type="subscription",
            subscription_item=item,
            price=item.price,
            description="%s (%s)"
            % (
                pricing.describe(item.price, item.quantity),
                describe_period(period_start, period_end),
            ),
            quantity=item.quantity,
            amount=pricing.amount_for_quantity(item.price, item.quantity),
            period_start=period_start,
            period_end=period_end,
        )


def attach_pending_items(invoice):
    """Move the customer's pending invoice items onto ``invoice``.

    Subscription invoices pick up items of that subscription plus items that
    are not tied to any subscription; manual invoices only pick up the latter.
    """
    query = InvoiceItem.query.filter(
        InvoiceItem.customer_id == invoice.customer.id,
        InvoiceItem.invoice_id.is_(None),
        InvoiceItem.currency == invoice.currency,
    )
    if invoice.subscription is not None:
        query = query.filter(
            or_(
                InvoiceItem.subscription_id == invoice.subscription.id,
                InvoiceItem.subscription_id.is_(None),
            )
        )
    else:
        query = query.filter(InvoiceItem.subscription_id.is_(None))

    attached = []
    for item in query.order_by(InvoiceItem.created_at, InvoiceItem.id).all():
        item.invoice = invoice
        _append_line(
            invoice,
            line_type="invoiceitem",
            invoice_item_id=item.id,
            price=item.price,
            description=item.description,
            quantity=item.quantity,
            amount=item.amount,
            proration=item.proration,
            period_start=item.period_start,
            period_end=item.period_end,
        )
        attached.append(item)
    return attached


def discard_draft(invoice):
    """Delete a draft invoice that should never be finalized, releasing its items."""
    for item in InvoiceItem.query.filter_by(invoice_id=invoice.id).all():
        item.invoice = None
    db.session.flush()
    db.session.delete(invoice)
    db.session.flush()


def compute_totals(invoice):
    """(Re)compute discounts, taxes and totals. Returns the applied discount, if any."""
    lines = sorted(invoice.lines, key=lambda line: line.position)
    discount = discounts.active_discount_for(invoice)
    coupon = discount.coupon if discount is not None else None
    invoice.coupon = coupon

    invoice.discount_total = discounts.apply_discount(lines, coupon, invoice.currency)
    taxes.apply_taxes(invoice, lines)

    invoice.subtotal = sum(line.amount for line in lines)
    invoice.tax_total = sum(line.tax_amount for line in lines)
    exclusive_tax = sum(line.tax_amount for line in lines if not line.tax_inclusive)
    invoice.total = invoice.subtotal - invoice.discount_total + exclusive_tax
    invoice.amount_due = max(invoice.total - invoice.amount_paid, 0)
    return discount
