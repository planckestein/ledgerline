from datetime import datetime, timedelta

import pytest

from ledgerline.billing import invoicing
from ledgerline.billing import subscriptions as service
from ledgerline.billing.renewal import run_billing_cycle
from ledgerline.errors import InvalidRequestError, InvalidStateTransition
from ledgerline.models import Invoice, InvoiceItem
from tests.support import factories

JUN_1 = datetime(2020, 6, 1, 12)
JUN_16 = datetime(2020, 6, 16, 12)
JUL_1 = datetime(2020, 7, 1, 12)


def pending_items(customer):
    return (
        InvoiceItem.query.filter_by(customer_id=customer.id, invoice_id=None)
        .order_by(InvoiceItem.id)
        .all()
    )


def invoices_of(subscription):
    return Invoice.query.filter_by(subscription_id=subscription.id).order_by(Invoice.id).all()


class TestCreate:
    def test_charges_first_invoice_in_advance(self, tenant, gateway):
        customer = factories.customer(tenant)
        sub = factories.subscribe(customer, factories.price(tenant, unit_amount=1000))

        assert sub.status == "active"
        assert (sub.current_period_start, sub.current_period_end) == (JUN_1, JUL_1)
        assert sub.billing_cycle_anchor == JUN_1
        [invoice] = invoices_of(sub)
        assert invoice.billing_reason == "subscription_create"
        assert invoice.status == "paid"
        assert invoice.total == 1000
        assert invoice.number == "%s-0001" % customer.invoice_prefix
        assert gateway.charges[-1]["amount"] == 1000
        assert customer.currency == "eur"

    def test_declined_first_payment_leaves_subscription_incomplete(self, tenant):
        customer = factories.customer(tenant, token="tok_chargeDeclined")
        sub = factories.subscribe(customer, factories.price(tenant))
        [invoice] = invoices_of(sub)
        assert sub.status == "incomplete"
        assert invoice.status == "open"
        assert invoice.next_payment_attempt is None

    def test_requires_a_payment_method_for_automatic_collection(self, tenant):
        customer = factories.customer(tenant, token=None)
        with pytest.raises(InvalidRequestError) as excinfo:
            factories.subscribe(customer, factories.price(tenant))
        assert excinfo.value.code == "missing_payment_method"

    def test_send_invoice_is_not_charged(self, tenant, gateway):
        customer = factories.customer(tenant, token=None)
        sub = factories.subscribe(
            customer, factories.price(tenant), collection_method="send_invoice"
        )
        [invoice] = invoices_of(sub)
        assert sub.status == "active"
        assert invoice.status == "open"
        assert invoice.due_date == JUN_1 + timedelta(days=30)
        assert gateway.charges == []

    def test_trial_defers_the_first_invoice(self, tenant, clock):
        customer = factories.customer(tenant)
        sub = factories.subscribe(customer, factories.price(tenant), trial_period_days=14)
        trial_end = JUN_1 + timedelta(days=14)

        assert sub.status == "trialing"
        assert sub.current_period_end == trial_end
        assert sub.billing_cycle_anchor == trial_end
        assert invoices_of(sub) == []

        clock.set(trial_end)
        run_billing_cycle()
        assert sub.status == "active"
        [invoice] = invoices_of(sub)
        assert invoice.period_start == trial_end
        assert invoice.period_end == datetime(2020, 7, 15, 12)
        assert invoice.total == 1000

    def test_rejects_mixed_currencies(self, tenant):
        customer = factories.customer(tenant)
        with pytest.raises(InvalidRequestError):
            factories.subscribe(
                customer,
                [factories.price(tenant, currency="eur"), factories.price(tenant, currency="usd")],
            )

    def test_rejects_customer_currency_mismatch(self, tenant):
        customer = factories.customer(tenant, currency="usd")
        with pytest.raises(InvalidRequestError):
            factories.subscribe(customer, factories.price(tenant, currency="eur"))

    def test_rejects_mixed_intervals(self, tenant):
        customer = factories.customer(tenant)
        with pytest.raises(InvalidRequestError):
            factories.subscribe(
                customer,
                [factories.price(tenant), factories.price(tenant, interval="year")],
            )

    def test_rejects_duplicate_prices(self, tenant):
        customer = factories.customer(tenant)
        price = factories.price(tenant)
        with pytest.raises(InvalidRequestError):
            factories.subscribe(customer, [price, price])

    def test_rejects_inactive_price(self, tenant):
        customer = factories.customer(tenant)
        price = factories.price(tenant)
        price.active = False
        with pytest.raises(InvalidRequestError):
            factories.subscribe(customer, price)


class TestChangeItems:
    def test_quantity_change_creates_prorations(self, tenant, clock):
        customer = factories.customer(tenant)
        price = factories.price(tenant, unit_amount=1000)
        sub = factories.subscribe(customer, (price, 1))

        clock.set(JUN_16)
        service.update_subscription_items(sub, [(price, 3)])

        items = pending_items(customer)
        assert [(i.amount, i.quantity, i.proration) for i in items] == [
            (-500, 1, True),
            (1500, 3, True),
        ]
        assert items[0].period_start == JUN_16
        assert items[0].period_end == JUL_1
        assert sub.active_items[0].quantity == 3

        clock.set(JUL_1)
        run_billing_cycle()
        renewal = invoices_of(sub)[-1]
        assert [line.amount for line in renewal.lines] == [3000, -500, 1500]
        assert renewal.total == 4000
        assert pending_items(customer) == []

    def test_swapping_prices_credits_old_and_charges_new(self, tenant, clock):
        customer = factories.customer(tenant)
        basic = factories.price(tenant, unit_amount=1000)
        pro = factories.price(tenant, unit_amount=2000)
        sub = factories.subscribe(customer, basic)

        clock.set(JUN_16)
        service.update_subscription_items(sub, [(pro, 1)])

        assert [i.amount for i in pending_items(customer)] == [-500, 1000]
        assert [item.price for item in sub.active_items] == [pro]
        assert len(sub.items) == 2  # the old item is soft-deleted

    def test_proration_behavior_none(self, tenant, clock):
        customer = factories.customer(tenant)
        price = factories.price(tenant)
        sub = factories.subscribe(customer, price)
        clock.set(JUN_16)
        service.update_subscription_items(sub, [(price, 2)], proration_behavior="none")
        assert pending_items(customer) == []

    def test_always_invoice_bills_prorations_immediately(self, tenant, clock, gateway):
        customer = factories.customer(tenant)
        price = factories.price(tenant, unit_amount=1000)
        sub = factories.subscribe(customer, price)
        clock.set(JUN_16)
        service.update_subscription_items(sub, [(price, 3)], proration_behavior="always_invoice")

        invoice = invoices_of(sub)[-1]
        assert invoice.billing_reason == "subscription_update"
        assert invoice.total == 1000
        assert invoice.status == "paid"
        assert gateway.charges[-1]["amount"] == 1000
        assert pending_items(customer) == []

    def test_no_prorations_while_trialing(self, tenant, clock):
        customer = factories.customer(tenant)
        price = factories.price(tenant)
        sub = factories.subscribe(customer, price, trial_period_days=30)
        clock.advance(days=3)
        service.update_subscription_items(sub, [(price, 5)])
        assert pending_items(customer) == []

    def test_cannot_update_canceled_subscription(self, tenant):
        customer = factories.customer(tenant)
        price = factories.price(tenant)
        sub = factories.subscribe(customer, price)
        service.cancel_subscription(sub)
        with pytest.raises(InvalidStateTransition):
            service.update_subscription_items(sub, [(price, 2)])


class TestCancel:
    def test_cancel_at_period_end(self, tenant, clock):
        customer = factories.customer(tenant)
        sub = factories.subscribe(customer, factories.price(tenant))
        service.schedule_cancellation(sub)
        assert sub.status == "active"

        clock.set(JUL_1 + timedelta(hours=1))
        run_billing_cycle()
        assert sub.status == "canceled"
        assert sub.ended_at == JUL_1
        assert len(invoices_of(sub)) == 1

    def test_cancel_immediately_with_proration(self, tenant, clock):
        customer = factories.customer(tenant)
        sub = factories.subscribe(customer, factories.price(tenant, unit_amount=1000))
        clock.set(JUN_16)
        service.cancel_subscription(sub, prorate=True)
        assert sub.status == "canceled"
        assert sub.ended_at == JUN_16
        assert [i.amount for i in pending_items(customer)] == [-500]

    def test_negative_final_invoice_keeps_credit_pending(self, tenant, clock):
        customer = factories.customer(tenant)
        sub = factories.subscribe(customer, factories.price(tenant, unit_amount=1000))
        clock.set(JUN_16)
        service.cancel_subscription(sub, prorate=True, invoice_now=True)
        assert len(invoices_of(sub)) == 1
        assert [i.amount for i in pending_items(customer)] == [-500]

    def test_cannot_cancel_twice(self, tenant):
        customer = factories.customer(tenant)
        sub = factories.subscribe(customer, factories.price(tenant))
        service.cancel_subscription(sub)
        with pytest.raises(InvalidStateTransition):
            service.cancel_subscription(sub)


def test_incomplete_subscription_activates_when_first_invoice_is_paid(tenant):
    from ledgerline.payments import service as payments

    customer = factories.customer(tenant, token="tok_chargeDeclined")
    sub = factories.subscribe(customer, factories.price(tenant))
    payments.attach_payment_method(customer, "tok_visa")
    invoicing.pay_invoice(invoices_of(sub)[0])
    assert sub.status == "active"
