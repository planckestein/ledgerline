import json
from decimal import Decimal

import pytest

from ledgerline.billing import tax
from ledgerline.models import TaxRate
from tests.support import factories


@pytest.fixture
def rates(tenant):
    return {
        "global": factories.tax_rate(tenant, "5", name="Global"),
        "de": factories.tax_rate(tenant, "19", country="DE", name="DE VAT"),
        "fr": factories.tax_rate(tenant, "20", country="FR", name="FR VAT"),
        "us_ca": factories.tax_rate(tenant, "7.25", country="US", state="CA", name="CA"),
        "us_ny": factories.tax_rate(tenant, "4", country="US", state="NY", name="NY"),
    }


def resolve(customer):
    return tax.resolve_tax_rate(customer)


def test_country_rate_beats_global(tenant, rates):
    assert resolve(factories.customer(tenant, country="DE")) == (rates["de"], tax.STANDARD)


def test_global_rate_as_fallback(tenant, rates):
    assert resolve(factories.customer(tenant, country="JP")) == (rates["global"], tax.STANDARD)


def test_state_rate_beats_country_rate(tenant, rates):
    factories.tax_rate(tenant, "1", country="US", name="US federal")
    customer = factories.customer(tenant, country="US", state="ca")
    assert resolve(customer) == (rates["us_ca"], tax.STANDARD)


def test_rates_for_other_states_are_ignored(tenant, rates):
    customer = factories.customer(tenant, country="US", state="TX")
    assert resolve(customer) == (rates["global"], tax.STANDARD)


def test_no_rate(tenant):
    assert resolve(factories.customer(tenant)) == (None, tax.NO_RATE)


def test_inactive_rates_are_ignored(tenant, rates):
    rates["de"].active = False
    assert resolve(factories.customer(tenant, country="DE"))[0] == rates["global"]


def test_exempt_customer(tenant, rates):
    assert resolve(factories.customer(tenant, tax_exempt=True)) == (None, tax.EXEMPT)


def test_eu_reverse_charge(tenant, rates):
    customer = factories.customer(tenant, country="FR", vat_id="FR40303265045")
    assert resolve(customer) == (None, tax.REVERSE_CHARGE)


def test_domestic_b2b_is_taxed(tenant, rates):
    customer = factories.customer(tenant, country="DE", vat_id="DE811907980")
    assert resolve(customer) == (rates["de"], tax.STANDARD)


def test_non_eu_vat_id_is_not_reverse_charged(tenant, rates):
    customer = factories.customer(tenant, country="GB", vat_id="GB980780684")
    assert resolve(customer) == (rates["global"], tax.STANDARD)


@pytest.mark.parametrize(
    "raw",
    [
        json.dumps({"street": "Unter den Linden 1", "zip": "10117", "country": "Germany"}),
        json.dumps({"line1": "Unter den Linden 1", "country": "de"}),
        "Unter den Linden 1, 10117 Berlin, DE",
        json.dumps("Unter den Linden 1, 10117 Berlin, Deutschland"),
    ],
)
def test_legacy_address_formats(tenant, rates, raw):
    customer = factories.customer(tenant, billing_address=raw)
    assert resolve(customer)[0] == rates["de"]


class TestComputeTax:
    def rate(self, percentage, inclusive=False):
        return TaxRate(percentage=Decimal(percentage), inclusive=inclusive)

    @pytest.mark.parametrize(
        "net,percentage,expected",
        [(1000, "19", 190), (1005, "19", 191), (999, "7.5", 75), (-500, "19", -95), (0, "19", 0)],
    )
    def test_exclusive_two_decimal_currency(self, net, percentage, expected):
        assert tax.compute_tax(net, self.rate(percentage), "eur") == expected

    @pytest.mark.parametrize(
        "net,percentage,currency,expected",
        [(1190, "19", "eur", 190), (1100, "10", "jpy", 100), (1050, "5", "kwd", 50)],
    )
    def test_inclusive(self, net, percentage, currency, expected):
        assert tax.compute_tax(net, self.rate(percentage, inclusive=True), currency) == expected

    def test_without_rate(self):
        assert tax.compute_tax(1000, None, "eur") == 0
