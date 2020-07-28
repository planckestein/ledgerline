from datetime import datetime, timedelta

import pytest

from ledgerline.billing import renewal, usage
from ledgerline.billing.renewal import run_billing_cycle
from ledgerline.errors import InvalidRequestError
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

    assert summary == {"subscriptions": 1, "invoices": 1, "errors": []}
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


def test_weekly_and_yearly_intervals(tenant, clock):
    customer = factories.customer(tenant)
    weekly = factories.subscribe(customer, factories.price(tenant, interval="week"))
    other = factories.customer(tenant)
    yearly = factories.subscribe(other, factories.price(tenant, interval="year"))
    assert weekly.current_period_end == datetime(2020, 6, 8, 12)
    assert yearly.current_period_end == datetime(2021, 6, 1, 12)
    clock.set(datetime(2020, 6, 15, 12))
    run_billing_cycle()
    assert weekly.current_period_end == datetime(2020, 6, 22, 12)
    assert yearly.current_period_end == datetime(2021, 6, 1, 12)


def test_metered_usage_is_billed_in_arrears(tenant, clock):
    customer = factories.customer(tenant)
    metered = factories.price(tenant, unit_amount=5, usage_type="metered")
    licensed = factories.price(tenant, unit_amount=1000)
    sub = factories.subscribe(customer, [licensed, metered])
    first = invoices_of(sub)[0]
    assert [line.amount for line in first.lines] == [1000]

    item = [i for i in sub.active_items if i.price is metered][0]
    clock.set(datetime(2020, 6, 5))
    usage.record_usage(item, 10)
    clock.set(datetime(2020, 6, 20))
    usage.record_usage(item, 20)

    clock.set(JUL_1)
    run_billing_cycle()
    invoice = invoices_of(sub)[-1]
    metered_line = [line for line in invoice.lines if line.price is metered][0]
    assert metered_line.quantity == 30
    assert metered_line.amount == 150
    assert (metered_line.period_start, metered_line.period_end) == (JUN_1, JUL_1)
    assert invoice.total == 1150


def test_usage_exactly_at_period_end_belongs_to_next_period(tenant, clock):
    customer = factories.customer(tenant)
    metered = factories.price(tenant, unit_amount=1, usage_type="metered")
    sub = factories.subscribe(customer, metered)
    item = sub.active_items[0]
    usage.record_usage(item, 3, timestamp=JUL_1 - timedelta(microseconds=1))
    with pytest.raises(InvalidRequestError):
        usage.record_usage(item, 4, timestamp=JUL_1)
    clock.set(JUL_1)
    run_billing_cycle()
    usage.record_usage(item, 4, timestamp=JUL_1)
    assert usage.aggregate_usage(item, JUN_1, JUL_1) == 3
    assert usage.aggregate_usage(item, JUL_1, AUG_1) == 4


@pytest.mark.parametrize("mode,expected", [("sum", 17), ("max", 9), ("last_during_period", 3)])
def test_usage_aggregation_modes(tenant, clock, mode, expected):
    customer = factories.customer(tenant)
    price = factories.price(tenant, usage_type="metered", aggregate_usage=mode)
    sub = factories.subscribe(customer, price)
    item = sub.active_items[0]
    for day, quantity in [(2, 5), (3, 9), (4, 3)]:
        usage.record_usage(item, quantity, timestamp=datetime(2020, 6, day))
    assert usage.aggregate_usage(item, JUN_1, JUL_1) == expected


def test_usage_validation(tenant):
    customer = factories.customer(tenant)
    sub = factories.subscribe(customer, factories.price(tenant))
    with pytest.raises(InvalidRequestError):
        usage.record_usage(sub.active_items[0], 1)


def test_usage_during_trial_is_not_billed(tenant, clock):
    customer = factories.customer(tenant)
    metered = factories.price(tenant, unit_amount=100, usage_type="metered")
    sub = factories.subscribe(customer, metered, trial_period_days=10)
    usage.record_usage(sub.active_items[0], 50)
    clock.set(JUN_1 + timedelta(days=10))
    run_billing_cycle()
    [invoice] = invoices_of(sub)
    assert invoice.total == 0
    assert invoice.status == "paid"


def test_package_pricing_on_renewal(tenant, clock):
    customer = factories.customer(tenant)
    price = factories.price(
        tenant, unit_amount=2500, usage_type="metered", billing_scheme="package", package_size=1000
    )
    sub = factories.subscribe(customer, price)
    usage.record_usage(sub.active_items[0], 2001)
    clock.set(JUL_1)
    run_billing_cycle()
    assert invoices_of(sub)[-1].total == 7500


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


def test_one_failing_subscription_does_not_block_the_run(db, tenant, clock, monkeypatch):
    first = factories.subscribe(factories.customer(tenant), factories.price(tenant))
    second = factories.subscribe(factories.customer(tenant), factories.price(tenant))
    db.session.commit()
    original = renewal.renew_subscription

    def flaky(subscription, now=None):
        if subscription.id == first.id:
            raise RuntimeError("boom")
        return original(subscription, now)

    monkeypatch.setattr(renewal, "renew_subscription", flaky)
    clock.set(JUL_1)
    summary = run_billing_cycle()
    assert summary["errors"] == [first.id]
    assert summary["subscriptions"] == 1
    assert len(invoices_of(second)) == 2
