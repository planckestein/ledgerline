from datetime import datetime

import pytest

from ledgerline.billing import invoicing
from ledgerline.errors import InvalidStateTransition, InvoiceError
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

        invoicing.pay_invoice(invoice)
        assert invoice.status == "paid"
        assert invoice.amount_paid == 4000
        assert invoice.amount_due == 0

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

    def test_negative_total_cannot_be_finalized(self, tenant):
        customer = factories.customer(tenant)
        invoice = manual_invoice(customer, 300, -500)
        with pytest.raises(InvoiceError) as excinfo:
            invoicing.finalize_invoice(invoice)
        assert excinfo.value.code == "invoice_negative_total"

    def test_zero_total_is_paid_on_finalize(self, tenant, gateway):
        invoice = manual_invoice(factories.customer(tenant), 500, -500)
        invoicing.finalize_invoice(invoice)
        assert invoice.status == "paid"
        assert gateway.charges == []

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

    def test_uncollectible_then_recovered(self, tenant):
        invoice = manual_invoice(factories.customer(tenant), 1000)
        invoicing.finalize_invoice(invoice)
        invoicing.mark_uncollectible(invoice)

        invoicing.pay_invoice(invoice)
        assert invoice.status == "paid"

    def test_paid_out_of_band_does_not_charge(self, tenant, gateway):
        invoice = manual_invoice(factories.customer(tenant), 1000)
        invoicing.finalize_invoice(invoice)
        invoicing.pay_invoice(invoice, paid_out_of_band=True)
        assert invoice.status == "paid"
        assert gateway.charges == []

    def test_send_invoice_due_date(self, tenant):
        invoice = manual_invoice(
            factories.customer(tenant), 1000, collection_method="send_invoice", days_until_due=14
        )
        invoicing.finalize_invoice(invoice)
        assert invoice.due_date == datetime(2020, 6, 15, 12)
