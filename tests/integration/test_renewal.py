from datetime import datetime, timedelta

from ledgerline.billing.renewal import run_billing_cycle
from ledgerline.models import Invoice
from tests.support import factories

JUN_1 = datetime(2020, 6, 1, 12)
JUL_1 = datetime(2020, 7, 1, 12)
AUG_1 = datetime(2020, 8, 1, 12)


def invoices_of(subscription):
    return Invoice.query.filter_by(subscription_id=subscription.id).order_by(Invoice.id).all()


def test_renews_monthly_subscription(tenant, clock, gateway):
    customer = factories.customer(tenant)
    sub = factories.subscribe(customer, factories.price(tenant, unit_amount=1000))

    clock.set(JUL_1)
    summary = run_billing_cycle()

    assert summary == {"subscriptions": 1, "invoices": 1}
    assert (sub.current_period_start, sub.current_period_end) == (JUL_1, AUG_1)
    renewal_invoice = invoices_of(sub)[-1]
    assert renewal_invoice.billing_reason == "subscription_cycle"
    assert (renewal_invoice.period_start, renewal_invoice.period_end) == (JUL_1, AUG_1)
    assert renewal_invoice.status == "paid"
    assert renewal_invoice.number.endswith("-0002")
    assert len(gateway.charges) == 2


def test_does_nothing_before_period_end(tenant, clock):
    customer = factories.customer(tenant)
    sub = factories.subscribe(customer, factories.price(tenant))
    clock.set(JUL_1 - timedelta(seconds=1))
    assert run_billing_cycle()["subscriptions"] == 0
    assert len(invoices_of(sub)) == 1


def test_catches_up_on_missed_periods(tenant, clock):
    customer = factories.customer(tenant)
    sub = factories.subscribe(customer, factories.price(tenant))
    clock.set(datetime(2020, 9, 15))
    summary = run_billing_cycle()
    assert summary["invoices"] == 3
    assert sub.current_period_start == datetime(2020, 9, 1, 12)
    assert sub.current_period_end == datetime(2020, 10, 1, 12)
    assert [i.period_start for i in invoices_of(sub)[1:]] == [
        JUL_1,
        AUG_1,
        datetime(2020, 9, 1, 12),
    ]


def test_failed_renewal_moves_subscription_to_past_due(tenant, clock):
    from ledgerline.payments import service as payments

    customer = factories.customer(tenant)
    sub = factories.subscribe(customer, factories.price(tenant))
    payments.attach_payment_method(customer, "tok_chargeDeclined")
    clock.set(JUL_1)
    run_billing_cycle()
    invoice = invoices_of(sub)[-1]
    assert sub.status == "past_due"
    assert invoice.status == "open"
    assert invoice.next_payment_attempt == JUL_1 + timedelta(days=3)
