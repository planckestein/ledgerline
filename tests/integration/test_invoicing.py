from datetime import datetime

import pytest

from ledgerline.billing import invoicing
from ledgerline.errors import InvalidStateTransition
from ledgerline.models import InvoiceItem
from tests.support import factories


def manual_invoice(customer, *amounts, **kwargs):
    for amount in amounts:
        factories.invoice_item(customer, amount)
    return invoicing.create_manual_invoice(customer, **kwargs)


class TestLifecycle:
    def test_manual_invoice_from_pending_items(self, tenant):
        customer = factories.customer(tenant)
        invoice = manual_invoice(customer, 1500, 2500)
        assert invoice.status == "draft"
        assert invoice.number is None
        assert [line.amount for line in invoice.lines] == [1500, 2500]
        assert invoice.total == 4000

        invoicing.finalize_invoice(invoice)
        assert invoice.status == "open"
        assert invoice.number == "%s-0001" % customer.invoice_prefix

    def test_numbers_are_sequential_per_customer(self, tenant):
        first = factories.customer(tenant)
        second = factories.customer(tenant)
        numbers = []
        for customer in (first, first, second):
            invoice = manual_invoice(customer, 100)
            invoicing.finalize_invoice(invoice)
            numbers.append(invoice.number)
        assert numbers[0].endswith("-0001")
        assert numbers[1].endswith("-0002")
        assert numbers[2] == "%s-0001" % second.invoice_prefix
        assert first.next_invoice_sequence == 3

    def test_cannot_finalize_twice(self, tenant):
        invoice = manual_invoice(factories.customer(tenant), 100)
        invoicing.finalize_invoice(invoice)
        with pytest.raises(InvalidStateTransition):
            invoicing.finalize_invoice(invoice)

    def test_void_open_invoice(self, tenant):
        invoice = manual_invoice(factories.customer(tenant), 1000)
        invoicing.finalize_invoice(invoice)
        invoicing.void_invoice(invoice)
        assert invoice.status == "void"

    def test_void_draft_releases_items(self, tenant):
        customer = factories.customer(tenant)
        invoice = manual_invoice(customer, 1000)
        invoicing.void_invoice(invoice)
        pending = InvoiceItem.query.filter_by(customer_id=customer.id, invoice_id=None).all()
        assert [item.amount for item in pending] == [1000]

    def test_paid_invoice_cannot_be_voided(self, tenant):
        invoice = manual_invoice(factories.customer(tenant), 1000)
        invoicing.finalize_invoice(invoice)
        invoicing.pay_invoice(invoice, paid_out_of_band=True)
        with pytest.raises(InvalidStateTransition):
            invoicing.void_invoice(invoice)

    def test_send_invoice_due_date(self, tenant):
        invoice = manual_invoice(
            factories.customer(tenant), 1000, collection_method="send_invoice", days_until_due=14
        )
        invoicing.finalize_invoice(invoice)
        assert invoice.due_date == datetime(2020, 6, 15, 12)
