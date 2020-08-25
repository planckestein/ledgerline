"""Journal postings for billing events.

Every posting must balance; :func:`post_entry` raises
:class:`~ledgerline.errors.LedgerImbalanceError` otherwise, which aborts the
surrounding transaction. An imbalance always means an invoice's totals are
inconsistent with its lines.
"""
from ledgerline import clock
from ledgerline.errors import LedgerImbalanceError
from ledgerline.extensions import db
from ledgerline.ledger import accounts
from ledgerline.models import JournalEntry, JournalLine


def debit(account, amount, customer_id=None):
    """A debit of ``amount`` (a negative amount becomes a credit)."""
    if account not in accounts.ACCOUNTS:
        raise ValueError("Unknown account %r" % (account,))
    if amount >= 0:
        return JournalLine(account=account, debit=amount, credit=0, customer_id=customer_id)
    return JournalLine(account=account, debit=0, credit=-amount, customer_id=customer_id)


def credit(account, amount, customer_id=None):
    """A credit of ``amount`` (a negative amount becomes a debit)."""
    return debit(account, -amount, customer_id)


def post_entry(tenant_id, currency, reference_type, reference_id, memo, lines):
    lines = [line for line in lines if line.debit or line.credit]
    total_debit = sum(line.debit for line in lines)
    total_credit = sum(line.credit for line in lines)
    if total_debit != total_credit:
        raise LedgerImbalanceError(
            "Journal entry for %s %s does not balance (debits=%d, credits=%d)"
            % (reference_type, reference_id, total_debit, total_credit)
        )
    entry = JournalEntry(
        tenant_id=tenant_id,
        currency=currency,
        reference_type=reference_type,
        reference_id=reference_id,
        memo=memo,
        posted_at=clock.utcnow(),
    )
    entry.lines.extend(lines)
    db.session.add(entry)
    return entry


def recognized_revenue(invoice):
    """Revenue of an invoice: net line amounts without any tax they contain."""
    return sum(
        line.amount - line.discount_amount - (line.tax_amount if line.tax_inclusive else 0)
        for line in invoice.lines
    )


def post_invoice_finalized(invoice):
    customer_id = invoice.customer_id
    return post_entry(
        invoice.tenant_id,
        invoice.currency,
        "invoice",
        invoice.public_id,
        "Invoice %s finalized" % invoice.number,
        [
            debit(accounts.ACCOUNTS_RECEIVABLE, invoice.total, customer_id),
            credit(accounts.REVENUE, recognized_revenue(invoice)),
            credit(accounts.TAX_PAYABLE, invoice.tax_total),
        ],
    )


def post_invoice_voided(invoice):
    customer_id = invoice.customer_id
    return post_entry(
        invoice.tenant_id,
        invoice.currency,
        "invoice_void",
        invoice.public_id,
        "Invoice %s voided" % invoice.number,
        [
            credit(accounts.ACCOUNTS_RECEIVABLE, invoice.total, customer_id),
            debit(accounts.REVENUE, recognized_revenue(invoice)),
            debit(accounts.TAX_PAYABLE, invoice.tax_total),
        ],
    )


def post_payment(invoice, amount, out_of_band=False, recover_write_off=False):
    customer_id = invoice.customer_id
    if recover_write_off:
        post_entry(
            invoice.tenant_id,
            invoice.currency,
            "write_off_recovery",
            invoice.public_id,
            "Recovered written-off invoice %s" % invoice.number,
            [
                debit(accounts.ACCOUNTS_RECEIVABLE, amount, customer_id),
                credit(accounts.BAD_DEBT, amount),
            ],
        )
    memo = "Payment for invoice %s" % invoice.number
    if out_of_band:
        memo += " (paid out of band)"
    return post_entry(
        invoice.tenant_id,
        invoice.currency,
        "payment",
        invoice.public_id,
        memo,
        [
            debit(accounts.CASH, amount),
            credit(accounts.ACCOUNTS_RECEIVABLE, amount, customer_id),
        ],
    )


def post_write_off(invoice, amount):
    return post_entry(
        invoice.tenant_id,
        invoice.currency,
        "write_off",
        invoice.public_id,
        "Invoice %s marked uncollectible" % invoice.number,
        [
            debit(accounts.BAD_DEBT, amount),
            credit(accounts.ACCOUNTS_RECEIVABLE, amount, invoice.customer_id),
        ],
    )
