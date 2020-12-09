"""LL-102 acceptance tests: discount allocation and currency-aware tax rounding."""
import itertools

import pytest

from ledgerline.billing import invoicing
from ledgerline.ledger import accounts, reports
from ledgerline.models import Invoice
from tests.support import factories


def invoice_for(customer, amounts, currency="eur"):
    for amount in amounts:
        factories.invoice_item(customer, amount, currency=currency)
    invoice = invoicing.create_manual_invoice(customer)
    invoicing.finalize_invoice(invoice)
    return invoice


def assert_invariants(invoice):
    lines = invoice.lines
    assert invoice.subtotal == sum(line.amount for line in lines)
    assert invoice.discount_total == sum(line.discount_amount for line in lines)
    assert invoice.tax_total == sum(line.tax_amount for line in lines)
    exclusive = sum(line.tax_amount for line in lines if not line.tax_inclusive)
    assert invoice.total == invoice.subtotal - invoice.discount_total + exclusive


def assert_ledger_balanced(tenant, currency):
    balance = reports.trial_balance(tenant.id, currency)
    assert balance["balanced"] is True


class TestPercentOffAllocation:
    def test_two_lines_of_ten_oh_five(self, tenant):
        customer = factories.customer(tenant)
        factories.customer_discount(customer, factories.coupon(tenant, percent_off=10))
        invoice = invoice_for(customer, [1005, 1005])
        assert invoice.status == "open"
        assert invoice.discount_total == 201
        assert [line.discount_amount for line in invoice.lines] == [101, 100]
        assert invoice.total == 1809
        assert_invariants(invoice)
        assert reports.receivable_balance(tenant.id, "eur") == 1809

    def test_ties_go_to_earlier_lines(self, tenant):
        customer = factories.customer(tenant)
        factories.customer_discount(customer, factories.coupon(tenant, percent_off=10))
        invoice = invoice_for(customer, [105, 105, 105])
        assert invoice.discount_total == 32
        assert [line.discount_amount for line in invoice.lines] == [11, 11, 10]
        assert invoice.total == 283

    def test_with_exclusive_tax(self, tenant):
        factories.tax_rate(tenant, "19", country="DE")
        customer = factories.customer(tenant)
        factories.customer_discount(customer, factories.coupon(tenant, percent_off=10))
        invoice = invoice_for(customer, [1005, 1005])
        assert [line.tax_amount for line in invoice.lines] == [172, 172]
        assert invoice.total == 2153
        assert_invariants(invoice)
        balances = reports.account_balances(tenant.id, "eur")
        assert balances[accounts.ACCOUNTS_RECEIVABLE] == 2153
        assert balances[accounts.REVENUE] == -1809
        assert balances[accounts.TAX_PAYABLE] == -344

    def test_credits_are_still_not_discounted(self, tenant):
        customer = factories.customer(tenant)
        factories.customer_discount(customer, factories.coupon(tenant, percent_off=10))
        invoice = invoice_for(customer, [1005, -200, 1005])
        assert [line.discount_amount for line in invoice.lines] == [101, 0, 100]
        assert invoice.total == 1609

    def test_subscription_signup_through_the_api(self, api):
        customer = api.post("/v1/customers", json={"address": {"country": "DE"}}).get_json()
        api.post("/v1/customers/%s/payment_methods" % customer["id"], json={"token": "tok_visa"})
        prices = []
        for name in ("Seats", "Storage"):
            product = api.post("/v1/products", json={"name": name}).get_json()
            prices.append(
                api.post(
                    "/v1/prices",
                    json={
                        "product": product["id"],
                        "currency": "eur",
                        "unit_amount": 1005,
                        "recurring": {"interval": "month"},
                    },
                ).get_json()
            )
        coupon = api.post("/v1/coupons", json={"percent_off": "10", "duration": "forever"})
        response = api.post(
            "/v1/subscriptions",
            json={
                "customer": customer["id"],
                "items": [{"price": p["id"]} for p in prices],
                "coupon": coupon.get_json()["id"],
            },
        )
        assert response.status_code == 201, response.get_json()
        assert response.get_json()["status"] == "active"
        [invoice] = api.get("/v1/invoices", customer=customer["id"]).get_json()["data"]
        assert (invoice["discount_total"], invoice["total"], invoice["status"]) == (
            201,
            1809,
            "paid",
        )
        balance = api.get("/v1/ledger/trial_balance", currency="eur").get_json()
        assert balance["balanced"] is True

    @pytest.mark.parametrize(
        "amounts,percent",
        list(
            itertools.product(
                [[1005, 1005], [333, 333, 334], [1, 1, 1, 1, 1, 1, 1], [999, 1, 12345, 7]],
                ["10", "15", "33.333", "12.5", "99.9"],
            )
        ),
    )
    def test_invariants_hold_for_many_baskets(self, tenant, amounts, percent):
        factories.tax_rate(tenant, "19", country="DE")
        customer = factories.customer(tenant)
        factories.customer_discount(customer, factories.coupon(tenant, percent_off=percent))
        invoice = invoice_for(customer, amounts)
        assert_invariants(invoice)
        assert_ledger_balanced(tenant, "eur")


class TestCurrencyExponents:
    @pytest.mark.parametrize(
        "currency,country,percentage,amount,expected_tax",
        [
            ("jpy", "JP", "10", 1000, 100),
            ("jpy", "JP", "10", 1234, 123),
            ("jpy", "JP", "8", 1250, 100),
            ("krw", "KR", "10", 9995, 1000),
            ("kwd", "KW", "5", 1234, 62),
            ("kwd", "KW", "5", 1250, 63),
            ("bhd", "BH", "10", 1, 0),
            ("eur", "DE", "19", 1005, 191),
            ("usd", "US", "7.25", 999, 72),
        ],
    )
    def test_exclusive_tax_is_rounded_to_one_minor_unit(
        self, tenant, currency, country, percentage, amount, expected_tax
    ):
        factories.tax_rate(tenant, percentage, country=country)
        customer = factories.customer(tenant, country=country)
        invoice = invoice_for(customer, [amount], currency=currency)
        assert invoice.tax_total == expected_tax
        assert invoice.total == amount + expected_tax
        assert_ledger_balanced(tenant, currency)

    def test_jpy_subscription_with_discount_and_tax(self, tenant):
        factories.tax_rate(tenant, "10", country="JP")
        customer = factories.customer(tenant, country="JP")
        coupon = factories.coupon(tenant, percent_off=15)
        price = factories.price(tenant, unit_amount=1999, currency="jpy")
        sub = factories.subscribe(customer, [(price, 3)], coupon=coupon)
        invoice = Invoice.query.filter_by(subscription_id=sub.id).one()
        assert invoice.subtotal == 5997
        assert invoice.discount_total == 900  # 899.55
        assert invoice.tax_total == 510  # 509.7
        assert invoice.total == 5607
        assert invoice.status == "paid"
        assert_ledger_balanced(tenant, "jpy")

    def test_inclusive_tax_is_unchanged(self, tenant):
        factories.tax_rate(tenant, "10", country="JP", inclusive=True)
        customer = factories.customer(tenant, country="JP")
        invoice = invoice_for(customer, [1100], currency="jpy")
        assert (invoice.tax_total, invoice.total) == (100, 1100)

    def test_amount_off_is_unchanged(self, tenant):
        customer = factories.customer(tenant)
        factories.customer_discount(
            customer, factories.coupon(tenant, amount_off=500, currency="eur")
        )
        invoice = invoice_for(customer, [1000, 2000])
        assert [line.discount_amount for line in invoice.lines] == [167, 333]
