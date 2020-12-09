"""LL-101 acceptance tests: anchor-based periods and second-precise prorations."""
from datetime import datetime, timedelta

import pytest

from ledgerline.billing import subscriptions as service
from ledgerline.billing.renewal import run_billing_cycle
from ledgerline.models import Invoice, InvoiceItem
from tests.support import factories


def renew_until(sub, clock, until):
    """Run the billing job at every period end until ``until``; return the period ends."""
    ends = [sub.current_period_end]
    while sub.current_period_end < until:
        clock.set(sub.current_period_end)
        run_billing_cycle()
        ends.append(sub.current_period_end)
    return ends


def cycle_invoices(sub):
    return (
        Invoice.query.filter_by(subscription_id=sub.id)
        .order_by(Invoice.id)
        .all()
    )


def pending_amounts(customer):
    items = (
        InvoiceItem.query.filter_by(customer_id=customer.id, invoice_id=None)
        .order_by(InvoiceItem.id)
        .all()
    )
    return [item.amount for item in items]


class TestAnchorAlignedPeriods:
    def test_monthly_anchor_on_the_31st(self, tenant, clock):
        clock.set(datetime(2020, 1, 31, 10))
        sub = factories.subscribe(factories.customer(tenant), factories.price(tenant))
        ends = renew_until(sub, clock, datetime(2020, 8, 1))
        assert ends == [
            datetime(2020, 2, 29, 10),
            datetime(2020, 3, 31, 10),
            datetime(2020, 4, 30, 10),
            datetime(2020, 5, 31, 10),
            datetime(2020, 6, 30, 10),
            datetime(2020, 7, 31, 10),
            datetime(2020, 8, 31, 10),
        ]
        assert sub.billing_cycle_anchor == datetime(2020, 1, 31, 10)

    def test_invoices_cover_contiguous_aligned_periods(self, tenant, clock):
        clock.set(datetime(2020, 1, 31, 10))
        sub = factories.subscribe(factories.customer(tenant), factories.price(tenant))
        renew_until(sub, clock, datetime(2020, 5, 1))
        periods = [(i.period_start, i.period_end) for i in cycle_invoices(sub)]
        assert periods == [
            (datetime(2020, 1, 31, 10), datetime(2020, 2, 29, 10)),
            (datetime(2020, 2, 29, 10), datetime(2020, 3, 31, 10)),
            (datetime(2020, 3, 31, 10), datetime(2020, 4, 30, 10)),
            (datetime(2020, 4, 30, 10), datetime(2020, 5, 31, 10)),
        ]

    def test_anchor_on_the_30th_through_february(self, tenant, clock):
        clock.set(datetime(2021, 1, 30, 8, 15))
        sub = factories.subscribe(factories.customer(tenant), factories.price(tenant))
        ends = renew_until(sub, clock, datetime(2021, 4, 1))
        assert ends == [
            datetime(2021, 2, 28, 8, 15),
            datetime(2021, 3, 30, 8, 15),
            datetime(2021, 4, 30, 8, 15),
        ]

    def test_quarterly_anchor_on_the_30th(self, tenant, clock):
        clock.set(datetime(2020, 11, 30))
        price = factories.price(tenant, interval="month", interval_count=3)
        sub = factories.subscribe(factories.customer(tenant), price)
        ends = renew_until(sub, clock, datetime(2021, 9, 1))
        assert ends == [
            datetime(2021, 2, 28),
            datetime(2021, 5, 30),
            datetime(2021, 8, 30),
            datetime(2021, 11, 30),
        ]

    def test_yearly_anchor_on_leap_day(self, tenant, clock):
        clock.set(datetime(2020, 2, 29, 23, 59, 59))
        price = factories.price(tenant, interval="year")
        sub = factories.subscribe(factories.customer(tenant), price)
        ends = renew_until(sub, clock, datetime(2024, 1, 1))
        assert ends == [
            datetime(2021, 2, 28, 23, 59, 59),
            datetime(2022, 2, 28, 23, 59, 59),
            datetime(2023, 2, 28, 23, 59, 59),
            datetime(2024, 2, 29, 23, 59, 59),
        ]

    def test_trial_ending_on_a_month_end(self, tenant, clock):
        clock.set(datetime(2020, 1, 1, 10))
        sub = factories.subscribe(
            factories.customer(tenant), factories.price(tenant), trial_period_days=30
        )
        assert sub.billing_cycle_anchor == datetime(2020, 1, 31, 10)
        ends = renew_until(sub, clock, datetime(2020, 4, 1))
        assert ends == [
            datetime(2020, 1, 31, 10),
            datetime(2020, 2, 29, 10),
            datetime(2020, 3, 31, 10),
            datetime(2020, 4, 30, 10),
        ]

    def test_catch_up_run_stays_aligned(self, tenant, clock):
        clock.set(datetime(2020, 1, 31, 10))
        sub = factories.subscribe(factories.customer(tenant), factories.price(tenant))
        clock.set(datetime(2020, 5, 15))
        run_billing_cycle()
        periods = [(i.period_start, i.period_end) for i in cycle_invoices(sub)[1:]]
        assert periods == [
            (datetime(2020, 2, 29, 10), datetime(2020, 3, 31, 10)),
            (datetime(2020, 3, 31, 10), datetime(2020, 4, 30, 10)),
            (datetime(2020, 4, 30, 10), datetime(2020, 5, 31, 10)),
        ]

    def test_unclamped_anchors_are_unchanged(self, tenant, clock):
        clock.set(datetime(2020, 1, 15, 9))
        sub = factories.subscribe(factories.customer(tenant), factories.price(tenant))
        ends = renew_until(sub, clock, datetime(2020, 4, 1))
        assert ends == [
            datetime(2020, 2, 15, 9),
            datetime(2020, 3, 15, 9),
            datetime(2020, 4, 15, 9),
        ]

    def test_api_exposes_aligned_period(self, api, clock):
        clock.set(datetime(2020, 1, 31, 10))
        customer = api.post("/v1/customers", json={}).get_json()
        api.post("/v1/customers/%s/payment_methods" % customer["id"], json={"token": "tok_visa"})
        product = api.post("/v1/products", json={"name": "Pro"}).get_json()
        price = api.post(
            "/v1/prices",
            json={
                "product": product["id"],
                "currency": "eur",
                "unit_amount": 1000,
                "recurring": {"interval": "month"},
            },
        ).get_json()
        sub = api.post(
            "/v1/subscriptions",
            json={"customer": customer["id"], "items": [{"price": price["id"]}]},
        ).get_json()
        for moment in (datetime(2020, 2, 29, 10), datetime(2020, 3, 31, 10)):
            clock.set(moment)
            run_billing_cycle()
        fetched = api.get("/v1/subscriptions/%s" % sub["id"]).get_json()
        assert fetched["current_period_start"] == 1585648800  # 2020-03-31 10:00 UTC
        assert fetched["current_period_end"] == 1588240800  # 2020-04-30 10:00 UTC


class TestProrationPrecision:
    def test_upgrade_is_prorated_to_the_second(self, tenant, clock):
        customer = factories.customer(tenant)
        price = factories.price(tenant, unit_amount=999)
        sub = factories.subscribe(customer, (price, 1))
        clock.set(datetime(2020, 6, 10, 18, 30))
        service.update_subscription_items(sub, [(price, 2)])
        assert pending_amounts(customer) == [-690, 1381]

    def test_daily_plan_changed_on_the_first_day(self, tenant, clock):
        customer = factories.customer(tenant)
        price = factories.price(tenant, unit_amount=2400, interval="day")
        sub = factories.subscribe(customer, (price, 1))
        clock.advance(hours=6)
        service.update_subscription_items(sub, [(price, 2)])
        assert pending_amounts(customer) == [-1800, 3600]

    def test_proration_in_a_month_end_period(self, tenant, clock):
        clock.set(datetime(2020, 1, 31, 10))
        customer = factories.customer(tenant)
        price = factories.price(tenant, unit_amount=3100)
        sub = factories.subscribe(customer, (price, 1))
        renew_until(sub, clock, datetime(2020, 3, 1))
        assert sub.current_period_end == datetime(2020, 3, 31, 10)
        clock.set(datetime(2020, 3, 16, 10))
        service.update_subscription_items(sub, [(price, 2)])
        assert pending_amounts(customer) == [-1500, 3000]

    def test_cancellation_credit_is_prorated_to_the_second(self, tenant, clock):
        customer = factories.customer(tenant)
        sub = factories.subscribe(customer, factories.price(tenant, unit_amount=1000))
        clock.set(datetime(2020, 6, 3, 0))
        service.cancel_subscription(sub, prorate=True)
        assert pending_amounts(customer) == [-950]

    @pytest.mark.parametrize("seconds", [1, 59, 3599])
    def test_changes_just_after_period_start_credit_almost_everything(
        self, tenant, clock, seconds
    ):
        customer = factories.customer(tenant)
        price = factories.price(tenant, unit_amount=259200000)  # 100 per second of the period
        sub = factories.subscribe(customer, (price, 1))
        clock.advance(seconds=seconds)
        service.update_subscription_items(sub, [(price, 2)], proration_behavior="create_prorations")
        credit, charge = pending_amounts(customer)
        assert credit == -(259200000 - 100 * seconds)
        assert charge == 2 * (259200000 - 100 * seconds)

    def test_change_at_period_boundary_has_no_proration(self, tenant, clock):
        customer = factories.customer(tenant)
        price = factories.price(tenant)
        sub = factories.subscribe(customer, (price, 1))
        clock.set(sub.current_period_end - timedelta(microseconds=1))
        service.update_subscription_items(sub, [(price, 2)])
        assert pending_amounts(customer) == []
