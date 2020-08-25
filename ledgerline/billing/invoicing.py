"""Invoice lifecycle: finalize, pay, void, mark uncollectible.

State machine::

    draft --finalize--> open --pay--> paid
      |                   |  \\
      +--void--> void <---+   +--mark_uncollectible--> uncollectible --pay--> paid

Every transition that changes what the customer owes posts a journal entry
(see ledgerline.ledger.posting) in the same transaction.
"""
from datetime import timedelta

from ledgerline import clock
from ledgerline.billing import discounts, invoice_builder
from ledgerline.errors import InvalidRequestError, InvalidStateTransition, InvoiceError
from ledgerline.extensions import db
from ledgerline.ledger import posting
from ledgerline.models import Customer, InvoiceItem

ALLOWED_TRANSITIONS = {
    "draft": ("open", "void"),
    "open": ("paid", "void", "uncollectible"),
    "uncollectible": ("paid",),
    "paid": (),
    "void": (),
}

REACTIVATING_STATUSES = ("past_due", "incomplete", "unpaid")


def _transition(invoice, target):
    if target not in ALLOWED_TRANSITIONS[invoice.status]:
        raise InvalidStateTransition(
            "Invoice %s cannot transition from %s to %s"
            % (invoice.public_id, invoice.status, target)
        )
    invoice.status = target


def create_manual_invoice(customer, collection_method="charge_automatically", days_until_due=None):
    """Create a draft invoice from the customer's pending, non-subscription invoice items."""
    if customer.currency is None:
        raise InvalidRequestError("Customer has nothing to invoice", param="customer")
    invoice = invoice_builder.create_draft(
        customer,
        currency=customer.currency,
        billing_reason="manual",
        collection_method=collection_method,
        days_until_due=days_until_due,
    )
    if not invoice_builder.attach_pending_items(invoice):
        invoice_builder.discard_draft(invoice)
        raise InvalidRequestError("Customer has no pending invoice items", param="customer")
    invoice_builder.compute_totals(invoice)
    db.session.flush()
    return invoice


def _allocate_number(customer):
    locked = Customer.query.filter_by(id=customer.id).with_for_update().populate_existing().one()
    sequence = locked.next_invoice_sequence
    locked.next_invoice_sequence = sequence + 1
    return "%s-%04d" % (locked.invoice_prefix, sequence)


def finalize_invoice(invoice):
    if invoice.status != "draft":
        raise InvalidStateTransition(
            "Only draft invoices can be finalized (invoice %s is %s)"
            % (invoice.public_id, invoice.status)
        )
    discount = invoice_builder.compute_totals(invoice)
    if invoice.total < 0:
        raise InvoiceError(
            "Invoice total cannot be negative (got %d)" % invoice.total,
            code="invoice_negative_total",
        )

    now = clock.utcnow()
    invoice.number = _allocate_number(invoice.customer)
    _transition(invoice, "open")
    invoice.finalized_at = now
    if invoice.collection_method == "send_invoice":
        invoice.due_date = now + timedelta(days=invoice.days_until_due or 30)
    else:
        invoice.due_date = now
    discounts.close_once_discount(discount, now)
    db.session.flush()

    posting.post_invoice_finalized(invoice)
    if invoice.total == 0:
        mark_paid(invoice, amount=0)
    return invoice


def mark_paid(invoice, amount, attempt=None, out_of_band=False):
    was_uncollectible = invoice.status == "uncollectible"
    _transition(invoice, "paid")
    now = clock.utcnow()
    invoice.amount_paid += amount
    invoice.amount_due = 0
    invoice.paid_at = now
    invoice.next_payment_attempt = None
    if amount:
        posting.post_payment(
            invoice, amount, out_of_band=out_of_band, recover_write_off=was_uncollectible
        )

    subscription = invoice.subscription
    if subscription is not None and subscription.status in REACTIVATING_STATUSES:
        subscription.status = "active"
    return invoice


def pay_invoice(invoice, paid_out_of_band=False):
    """Collect payment for an open (or uncollectible) invoice now."""
    if invoice.status not in ("open", "uncollectible"):
        raise InvalidStateTransition(
            "Invoice %s is %s and cannot be paid" % (invoice.public_id, invoice.status)
        )
    if paid_out_of_band:
        return mark_paid(invoice, amount=invoice.amount_due, out_of_band=True)

    from ledgerline.payments import service as payment_service

    attempt = payment_service.collect_invoice(invoice)
    return attempt


def void_invoice(invoice):
    was_finalized = invoice.status != "draft"
    _transition(invoice, "void")
    invoice.voided_at = clock.utcnow()
    invoice.next_payment_attempt = None
    invoice.amount_due = 0
    if was_finalized:
        posting.post_invoice_voided(invoice)
    else:
        # A voided draft never existed for the customer: give its items back.
        for item in InvoiceItem.query.filter_by(invoice_id=invoice.id).all():
            item.invoice = None
    return invoice


def mark_uncollectible(invoice):
    _transition(invoice, "uncollectible")
    invoice.marked_uncollectible_at = clock.utcnow()
    invoice.next_payment_attempt = None
    posting.post_write_off(invoice, invoice.amount_due)
    return invoice
