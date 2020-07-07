import pytest

from ledgerline.billing import pricing
from ledgerline.models import Price, Product


def make_price(**fields):
    defaults = dict(
        currency="usd",
        unit_amount=500,
        billing_scheme="per_unit",
        interval="month",
        interval_count=1,
        usage_type="licensed",
    )
    defaults.update(fields)
    price = Price(**defaults)
    price.product = Product(name="Seats")
    return price


def test_per_unit():
    assert pricing.amount_for_quantity(make_price(), 3) == 1500
    assert pricing.amount_for_quantity(make_price(), 0) == 0


@pytest.mark.parametrize("quantity,expected", [(0, 0), (1, 2000), (1000, 2000), (1001, 4000)])
def test_package_rounds_up(quantity, expected):
    price = make_price(billing_scheme="package", package_size=1000, unit_amount=2000)
    assert pricing.amount_for_quantity(price, quantity) == expected


def test_negative_quantity_is_rejected():
    with pytest.raises(ValueError):
        pricing.amount_for_quantity(make_price(), -1)


def test_unknown_scheme_is_rejected():
    with pytest.raises(ValueError):
        pricing.amount_for_quantity(make_price(billing_scheme="stairs"), 1)


def test_describe():
    assert pricing.describe(make_price(), 2) == "2 × Seats"
    assert pricing.describe(make_price(nickname="Annual"), 1) == "1 × Seats (Annual)"
