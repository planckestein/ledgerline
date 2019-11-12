"""Turn a price and a quantity into an amount."""

BILLING_SCHEMES = ("per_unit", "package")


def amount_for_quantity(price, quantity):
    """Amount in minor units charged for ``quantity`` units of ``price`` for one period."""
    if quantity < 0:
        raise ValueError("quantity must not be negative")
    if price.billing_scheme == "per_unit":
        return price.unit_amount * quantity
    if price.billing_scheme == "package":
        if quantity == 0:
            return 0
        packages = -(-quantity // price.package_size)
        return packages * price.unit_amount
    raise ValueError("Unsupported billing scheme %r" % (price.billing_scheme,))


def describe(price, quantity):
    name = price.product.name if price.product is not None else price.public_id
    if price.nickname:
        name = "%s (%s)" % (name, price.nickname)
    return "%d × %s" % (quantity, name)
