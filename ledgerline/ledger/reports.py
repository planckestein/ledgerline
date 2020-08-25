"""Ledger reports."""
from sqlalchemy import func

from ledgerline.extensions import db
from ledgerline.ledger import accounts
from ledgerline.models import JournalEntry, JournalLine


def account_balances(tenant_id, currency, customer_id=None):
    """``{account: debits - credits}`` for every account with activity."""
    query = (
        db.session.query(
            JournalLine.account,
            func.coalesce(func.sum(JournalLine.debit), 0),
            func.coalesce(func.sum(JournalLine.credit), 0),
        )
        .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
        .filter(JournalEntry.tenant_id == tenant_id, JournalEntry.currency == currency)
    )
    if customer_id is not None:
        query = query.filter(JournalLine.customer_id == customer_id)
    rows = query.group_by(JournalLine.account).all()
    return {account: int(debits) - int(credits) for account, debits, credits in rows}


def trial_balance(tenant_id, currency):
    query = (
        db.session.query(
            JournalLine.account,
            func.coalesce(func.sum(JournalLine.debit), 0),
            func.coalesce(func.sum(JournalLine.credit), 0),
        )
        .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
        .filter(JournalEntry.tenant_id == tenant_id, JournalEntry.currency == currency)
        .group_by(JournalLine.account)
        .order_by(JournalLine.account)
    )
    rows = []
    total_debits = total_credits = 0
    for account, debits, credits in query.all():
        debits, credits = int(debits), int(credits)
        total_debits += debits
        total_credits += credits
        rows.append(
            {
                "account": account,
                "type": accounts.ACCOUNTS.get(account, "unknown"),
                "debits": debits,
                "credits": credits,
                "balance": debits - credits,
            }
        )
    return {
        "currency": currency,
        "accounts": rows,
        "total_debits": total_debits,
        "total_credits": total_credits,
        "balanced": total_debits == total_credits,
    }


def receivable_balance(tenant_id, currency, customer_id=None):
    balances = account_balances(tenant_id, currency, customer_id=customer_id)
    return balances.get(accounts.ACCOUNTS_RECEIVABLE, 0)
