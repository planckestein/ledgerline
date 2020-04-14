from datetime import datetime

import pytest

from ledgerline.billing import invoicing
from ledgerline.billing.renewal import run_billing_cycle
from ledgerline.errors import InvalidStateTransition, InvoiceError
from ledgerline.models import Invoice, InvoiceItem
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


class TestTotals:
    def test_percent_off_across_lines(self, tenant):
        customer = factories.customer(tenant)
        factories.customer_discount(customer, factories.coupon(tenant, percent_off=10))
        invoice = manual_invoice(customer, 1000, 3000)
        assert [line.discount_amount for line in invoice.lines] == [100, 300]
        assert invoice.total == 3600

    def test_amount_off_is_allocated_proportionally(self, tenant):
        customer = factories.customer(tenant)
        factories.customer_discount(
            customer, factories.coupon(tenant, amount_off=500, currency="eur")
        )
        invoice = manual_invoice(customer, 1000, 2000)
        assert [line.discount_amount for line in invoice.lines] == [167, 333]
        assert invoice.discount_total == 500
        assert invoice.total == 2500

    def test_amount_off_is_capped_at_subtotal(self, tenant):
        customer = factories.customer(tenant)
        factories.customer_discount(
            customer, factories.coupon(tenant, amount_off=5000, currency="eur")
        )
        invoice = manual_invoice(customer, 1200)
        assert invoice.discount_total == 1200
        assert invoice.total == 0

    def test_amount_off_in_other_currency_is_ignored(self, tenant):
        customer = factories.customer(tenant)
        factories.customer_discount(
            customer, factories.coupon(tenant, amount_off=500, currency="usd")
        )
        invoice = manual_invoice(customer, 1200)
        assert invoice.discount_total == 0

    def test_credits_are_not_discounted(self, tenant):
        customer = factories.customer(tenant)
        factories.customer_discount(customer, factories.coupon(tenant, percent_off=10))
        invoice = manual_invoice(customer, 1000, -300)
        assert [line.discount_amount for line in invoice.lines] == [100, 0]
        assert invoice.total == 600


class TestCouponDuration:
    def _subscription(self, tenant, coupon):
        customer = factories.customer(tenant)
        return factories.subscribe(
            customer, factories.price(tenant, unit_amount=1000), coupon=coupon
        )

    def _totals(self, sub):
        invoices = Invoice.query.filter_by(subscription_id=sub.id).order_by(Invoice.id).all()
        return [invoice.total for invoice in invoices]

    def test_once(self, tenant, clock):
        sub = self._subscription(tenant, factories.coupon(tenant, percent_off=50, duration="once"))
        clock.set(datetime(2020, 8, 1, 12))
        run_billing_cycle()
        assert self._totals(sub) == [500, 1000, 1000]

    def test_repeating(self, tenant, clock):
        coupon = factories.coupon(
            tenant, percent_off=50, duration="repeating", duration_in_months=2
        )
        sub = self._subscription(tenant, coupon)
        clock.set(datetime(2020, 9, 1, 12))
        run_billing_cycle()
        assert self._totals(sub) == [500, 500, 1000, 1000]

    def test_forever(self, tenant, clock):
        sub = self._subscription(tenant, factories.coupon(tenant, percent_off=50))
        clock.set(datetime(2020, 8, 1, 12))
        run_billing_cycle()
        assert self._totals(sub) == [500, 500, 500]

    def test_subscription_discount_beats_customer_discount(self, tenant):
        customer = factories.customer(tenant)
        factories.customer_discount(customer, factories.coupon(tenant, percent_off=10))
        sub = factories.subscribe(
            customer, factories.price(tenant), coupon=factories.coupon(tenant, percent_off=30)
        )
        invoice = Invoice.query.filter_by(subscription_id=sub.id).one()
        assert invoice.discount_total == 300

    def test_max_redemptions(self, tenant):
        from ledgerline.errors import InvalidRequestError

        coupon = factories.coupon(tenant, percent_off=10, max_redemptions=1)
        factories.customer_discount(factories.customer(tenant), coupon)
        assert coupon.valid is False
        with pytest.raises(InvalidRequestError):
            factories.customer_discount(factories.customer(tenant), coupon)
