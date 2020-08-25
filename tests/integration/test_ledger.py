from datetime import datetime

import pytest

from ledgerline.billing.renewal import run_billing_cycle
from ledgerline.errors import LedgerImbalanceError
from ledgerline.ledger import accounts, posting, reports
from ledgerline.models import Invoice, JournalEntry
from tests.support import factories


def assert_every_entry_balances():
    for entry in JournalEntry.query.all():
        assert sum(x.debit for x in entry.lines) == sum(x.credit for x in entry.lines), entry.memo


def test_trial_balance_after_a_billing_cycle(tenant, clock):
    factories.tax_rate(tenant, "19", country="DE")
    for _ in range(3):
        factories.subscribe(factories.customer(tenant), factories.price(tenant, unit_amount=1000))
    clock.set(datetime(2020, 7, 1, 12))
    run_billing_cycle()

    balance = reports.trial_balance(tenant.id, "eur")
    assert balance["balanced"] is True
    by_account = {row["account"]: row["balance"] for row in balance["accounts"]}
    assert by_account[accounts.CASH] == 6 * 1190
    assert by_account[accounts.REVENUE] == -6 * 1000
    assert by_account[accounts.TAX_PAYABLE] == -6 * 190
    assert by_account[accounts.ACCOUNTS_RECEIVABLE] == 0
    assert_every_entry_balances()


def test_receivables_match_open_invoices(tenant):
    customer = factories.customer(tenant, token=None)
    other = factories.customer(tenant, token=None)
    factories.subscribe(
        customer, factories.price(tenant, unit_amount=700), collection_method="send_invoice"
    )
    factories.subscribe(
        other, factories.price(tenant, unit_amount=300), collection_method="send_invoice"
    )
    open_total = sum(i.total for i in Invoice.query.filter_by(status="open"))
    assert reports.receivable_balance(tenant.id, "eur") == open_total == 1000
    assert reports.receivable_balance(tenant.id, "eur", customer_id=customer.id) == 700


def test_ledgers_are_per_currency(tenant):
    factories.subscribe(factories.customer(tenant), factories.price(tenant, currency="eur"))
    factories.subscribe(
        factories.customer(tenant), factories.price(tenant, currency="usd", unit_amount=99)
    )
    assert reports.account_balances(tenant.id, "usd")[accounts.CASH] == 99
    assert reports.account_balances(tenant.id, "eur")[accounts.CASH] == 1000


def test_unbalanced_entries_are_rejected(tenant):
    with pytest.raises(LedgerImbalanceError):
        posting.post_entry(
            tenant.id,
            "eur",
            "manual",
            "x",
            "broken",
            [posting.debit(accounts.CASH, 100), posting.credit(accounts.REVENUE, 99)],
        )


def test_negative_amounts_flip_sides():
    line = posting.debit(accounts.CASH, -50)
    assert (line.debit, line.credit) == (0, 50)
    line = posting.credit(accounts.REVENUE, -50)
    assert (line.debit, line.credit) == (50, 0)


def test_unknown_account():
    with pytest.raises(ValueError):
        posting.debit("9999_suspense", 1)
