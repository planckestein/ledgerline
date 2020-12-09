"""LL-105 acceptance tests: graduated and volume tiered prices."""
from datetime import datetime

import pytest
from sqlalchemy import inspect, text

from ledgerline.billing import subscriptions as service
from ledgerline.billing import usage
from ledgerline.billing.renewal import run_billing_cycle
from ledgerline.extensions import db as _db
from ledgerline.models import Invoice, InvoiceItem, Price
from tests.support import factories
from tests.support.migrations import downgrade, migration_app, schema_diff, upgrade

V141_HEAD = "f3b9d2e6a399"
API_TIERS = [
    {"up_to": 1000, "unit_amount": 10},
    {"up_to": 5000, "unit_amount": 7},
    {"up_to": "inf", "unit_amount": 5, "flat_amount": 1000},
]
SEAT_TIERS = [{"up_to": 5, "unit_amount": 1000}, {"up_to": "inf", "unit_amount": 800}]


def create_product(api):
    return api.post("/v1/products", json={"name": "API calls"}).get_json()["id"]


def price_body(product, mode="graduated", tiers=None, usage_type="metered", **extra):
    body = {
        "product": product,
        "currency": "eur",
        "billing_scheme": "tiered",
        "tiers_mode": mode,
        "tiers": API_TIERS if tiers is None else tiers,
        "recurring": {"interval": "month", "usage_type": usage_type},
    }
    body.update(extra)
    return body


def create_tiered_price(api, **kwargs):
    response = api.post("/v1/prices", json=price_body(create_product(api), **kwargs))
    assert response.status_code == 201, response.get_json()
    return response.get_json()


def load_price(public_id):
    return Price.query.filter_by(public_id=public_id).one()


def subscribe(tenant, price, quantity=1, **kwargs):
    customer = factories.customer(tenant)
    return factories.subscribe(customer, [(price, quantity)], **kwargs)


def invoices(sub):
    return Invoice.query.filter_by(subscription_id=sub.id).order_by(Invoice.id).all()


class TestApi:
    def test_create_and_retrieve(self, api):
        price = create_tiered_price(api)
        assert price["billing_scheme"] == "tiered"
        assert price["tiers_mode"] == "graduated"
        assert price["unit_amount"] is None
        expected = [
            {"up_to": 1000, "unit_amount": 10, "flat_amount": 0},
            {"up_to": 5000, "unit_amount": 7, "flat_amount": 0},
            {"up_to": None, "unit_amount": 5, "flat_amount": 1000},
        ]
        assert price["tiers"] == expected
        assert api.get("/v1/prices/%s" % price["id"]).get_json() == price
        listed = api.get("/v1/prices").get_json()["data"]
        assert listed[0]["tiers"] == expected

    def test_flat_prices_expose_null_tiers(self, api):
        response = api.post(
            "/v1/prices",
            json={
                "product": create_product(api),
                "currency": "eur",
                "unit_amount": 500,
                "recurring": {"interval": "month"},
            },
        )
        body = response.get_json()
        assert (body["tiers_mode"], body["tiers"], body["unit_amount"]) == (None, None, 500)

    @pytest.mark.parametrize(
        "overrides,param",
        [
            ({"tiers_mode": None}, "tiers_mode"),
            ({"tiers_mode": "stairs"}, "tiers_mode"),
            ({"unit_amount": 100}, "unit_amount"),
            ({"tiers": []}, "tiers"),
            ({"tiers": None}, "tiers"),
            ({"tiers": [{"up_to": 10, "unit_amount": 1}]}, "tiers"),
            ({"tiers": [{"up_to": "inf", "unit_amount": 1}, {"up_to": "inf"}]}, "tiers"),
            ({"tiers": [{"up_to": "inf"}, {"up_to": 10, "unit_amount": 1}]}, "tiers"),
            ({"tiers": [{"up_to": 10}, {"up_to": 10}, {"up_to": "inf"}]}, "tiers"),
            ({"tiers": [{"up_to": 10}, {"up_to": 5}, {"up_to": "inf"}]}, "tiers"),
            ({"tiers": [{"up_to": 0}, {"up_to": "inf"}]}, "tiers"),
            ({"tiers": [{"up_to": "inf", "unit_amount": -1}]}, "tiers"),
            ({"tiers": [{"up_to": "inf", "flat_amount": -5}]}, "tiers"),
            ({"tiers": [{"up_to": "lots"}]}, "tiers"),
            ({"tiers": [{"up_to": i + 1} for i in range(25)] + [{"up_to": "inf"}]}, "tiers"),
        ],
    )
    def test_validation(self, api, overrides, param):
        body = price_body(create_product(api))
        for key, value in overrides.items():
            if value is None:
                body.pop(key)
            else:
                body[key] = value
        response = api.post("/v1/prices", json=body)
        assert response.status_code == 400, response.get_json()
        assert response.get_json()["error"]["param"].startswith(param)

    @pytest.mark.parametrize(
        "extra,param",
        [
            ({"tiers_mode": "volume"}, "tiers_mode"),
            ({"tiers": SEAT_TIERS}, "tiers"),
        ],
    )
    def test_tier_fields_are_rejected_for_other_schemes(self, api, extra, param):
        body = {
            "product": create_product(api),
            "currency": "eur",
            "unit_amount": 100,
            "recurring": {"interval": "month"},
        }
        body.update(extra)
        response = api.post("/v1/prices", json=body)
        assert response.status_code == 400
        assert response.get_json()["error"]["param"] == param

    def test_unit_amount_still_required_for_per_unit(self, api):
        response = api.post(
            "/v1/prices",
            json={"product": create_product(api), "currency": "eur", "recurring": {"interval": "month"}},
        )
        assert response.get_json()["error"]["param"] == "unit_amount"

    def test_twenty_five_tiers_are_allowed(self, api):
        tiers = [{"up_to": i + 1, "unit_amount": 1} for i in range(24)] + [{"up_to": "inf"}]
        price = create_tiered_price(api, tiers=tiers)
        assert len(price["tiers"]) == 25


class TestMeteredAmounts:
    @pytest.mark.parametrize(
        "mode,quantity,expected",
        [
            ("graduated", 0, 0),
            ("graduated", 1, 10),
            ("graduated", 1000, 10000),
            ("graduated", 1001, 10007),
            ("graduated", 5000, 38000),
            ("graduated", 5001, 39005),
            ("graduated", 6200, 45000),
            ("volume", 0, 0),
            ("volume", 1000, 10000),
            ("volume", 1001, 7007),
            ("volume", 5000, 35000),
            ("volume", 6200, 32000),
        ],
    )
    def test_usage_is_billed_by_tier(self, api, tenant, clock, mode, quantity, expected):
        price = load_price(create_tiered_price(api, mode=mode)["id"])
        sub = subscribe(tenant, price)
        if quantity:
            usage.record_usage(sub.active_items[0], quantity)
        clock.set(datetime(2020, 7, 1, 12))
        run_billing_cycle()
        renewal = invoices(sub)[-1]
        [line] = renewal.lines
        assert (line.quantity, line.amount) == (quantity, expected)
        assert renewal.total == expected


class TestLicensedAmounts:
    def test_graduated_seats_on_first_invoice(self, api, tenant):
        price = load_price(create_tiered_price(api, tiers=SEAT_TIERS, usage_type="licensed")["id"])
        sub = subscribe(tenant, price, quantity=12)
        [invoice] = invoices(sub)
        assert [(line.quantity, line.amount) for line in invoice.lines] == [(12, 10600)]
        assert invoice.status == "paid"

    def test_volume_with_flat_fee_tier(self, api, tenant):
        tiers = [
            {"up_to": 10, "unit_amount": 0, "flat_amount": 5000},
            {"up_to": "inf", "unit_amount": 400},
        ]
        price = load_price(
            create_tiered_price(api, mode="volume", tiers=tiers, usage_type="licensed")["id"]
        )
        assert [invoices(subscribe(tenant, price, quantity=q))[0].total for q in (3, 10, 11)] == [
            5000,
            5000,
            4400,
        ]

    def test_quantity_change_prorates_tiered_amounts(self, api, tenant, clock):
        price = load_price(create_tiered_price(api, tiers=SEAT_TIERS, usage_type="licensed")["id"])
        sub = subscribe(tenant, price, quantity=12)
        clock.set(datetime(2020, 6, 16, 12))
        service.update_subscription_items(sub, [(price, 20)])
        pending = (
            InvoiceItem.query.filter_by(subscription_id=sub.id, invoice_id=None)
            .order_by(InvoiceItem.id)
            .all()
        )
        assert [item.amount for item in pending] == [-5300, 8500]
        clock.set(datetime(2020, 7, 1, 12))
        run_billing_cycle()
        assert invoices(sub)[-1].total == 17000 - 5300 + 8500

    def test_discount_and_tax_apply_to_tiered_lines(self, api, tenant):
        factories.tax_rate(tenant, "19", country="DE")
        price = load_price(create_tiered_price(api, tiers=SEAT_TIERS, usage_type="licensed")["id"])
        coupon = factories.coupon(tenant, percent_off=10)
        sub = subscribe(tenant, price, quantity=12, coupon=coupon)
        [invoice] = invoices(sub)
        assert invoice.discount_total == 1060
        assert invoice.tax_total == 1813
        assert invoice.total == 11353

    def test_flat_prices_are_unchanged(self, tenant):
        per_unit = factories.price(tenant, unit_amount=250)
        package = factories.price(
            tenant, unit_amount=2000, billing_scheme="package", package_size=10
        )
        assert invoices(subscribe(tenant, per_unit, quantity=4))[0].total == 1000
        assert invoices(subscribe(tenant, package, quantity=11))[0].total == 4000


class TestMigration:
    def test_schema_at_head(self):
        with migration_app() as (app, config):
            upgrade(config, "head")
            inspector = inspect(_db.engine)
            columns = {c["name"]: c for c in inspector.get_columns("price_tiers")}
            assert set(columns) >= {"id", "price_id", "position", "up_to", "unit_amount", "flat_amount"}
            assert columns["up_to"]["nullable"] is True
            prices = {c["name"]: c for c in inspector.get_columns("prices")}
            assert "tiers_mode" in prices
            assert prices["unit_amount"]["nullable"] is True
            assert schema_diff() == []

    def test_existing_prices_survive_and_downgrade_works(self):
        with migration_app() as (app, config):
            upgrade(config, V141_HEAD)
            now = datetime(2020, 10, 1, 12)
            with _db.engine.begin() as connection:
                connection.execute(
                    text(
                        "INSERT INTO tenants (id, public_id, name, home_country, default_currency, "
                        "dunning_retry_days, dunning_final_action, created_at, updated_at) "
                        "VALUES (1, 'acct_1', 'T', 'DE', 'eur', '3,5,7', 'cancel', :now, :now)"
                    ),
                    now=now,
                )
                connection.execute(
                    text(
                        "INSERT INTO products (id, public_id, tenant_id, name, active, created_at, "
                        "updated_at) VALUES (1, 'prod_1', 1, 'P', 1, :now, :now)"
                    ),
                    now=now,
                )
                connection.execute(
                    text(
                        "INSERT INTO prices (id, public_id, tenant_id, product_id, currency, "
                        "unit_amount, billing_scheme, interval, interval_count, usage_type, active, "
                        "created_at, updated_at) VALUES (1, 'price_1', 1, 1, 'eur', 1234, "
                        "'per_unit', 'month', 1, 'licensed', 1, :now, :now)"
                    ),
                    now=now,
                )
            upgrade(config, "head")
            with _db.engine.begin() as connection:
                row = connection.execute(
                    text("SELECT unit_amount, tiers_mode FROM prices WHERE id = 1")
                ).fetchone()
            assert (row[0], row[1]) == (1234, None)
            downgrade(config, V141_HEAD)
            assert "price_tiers" not in inspect(_db.engine).get_table_names()
            upgrade(config, "head")
            assert schema_diff() == []
