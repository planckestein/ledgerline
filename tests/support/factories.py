"""Factories that build valid domain objects through the service layer.

They flush but never commit; tests decide when a transaction ends.
"""
import itertools

from ledgerline.billing import subscriptions
from ledgerline.extensions import db
from ledgerline.geo import serialize_address
from ledgerline.models import ApiKey, Customer, InvoiceItem, Price, Product, Tenant
from ledgerline.payments import service as payment_service

_counter = itertools.count(1)


def tenant(name="Acme GmbH", home_country="DE", default_currency="eur", **fields):
    obj = Tenant(name=name, home_country=home_country, default_currency=default_currency, **fields)
    db.session.add(obj)
    db.session.flush()
    return obj


def api_key(tenant):
    _, secret = ApiKey.issue(tenant)
    db.session.flush()
    return secret


def customer(
    tenant,
    email=None,
    country="DE",
    state=None,
    token="tok_visa",
    currency=None,
    billing_address=None,
):
    if billing_address is None:
        billing_address = serialize_address({"country": country, "state": state})
    obj = Customer(
        tenant_id=tenant.id,
        email=email or "customer%d@example.com" % next(_counter),
        name="Customer",
        billing_address=billing_address,
        currency=currency,
    )
    db.session.add(obj)
    db.session.flush()
    if token:
        payment_service.attach_payment_method(obj, token)
        db.session.flush()
    return obj


def product(tenant, name=None):
    obj = Product(tenant_id=tenant.id, name=name or "Product %d" % next(_counter), active=True)
    db.session.add(obj)
    db.session.flush()
    return obj


def price(
    tenant,
    unit_amount=1000,
    currency="eur",
    interval="month",
    interval_count=1,
    billing_scheme="per_unit",
    package_size=None,
    product_obj=None,
    nickname=None,
):
    obj = Price(
        tenant_id=tenant.id,
        product=product_obj or product(tenant),
        currency=currency,
        unit_amount=unit_amount,
        interval=interval,
        interval_count=interval_count,
        billing_scheme=billing_scheme,
        package_size=package_size,
        nickname=nickname,
        active=True,
    )
    db.session.add(obj)
    db.session.flush()
    return obj


def subscribe(customer, items, **kwargs):
    """``items`` is a Price, or a list of Price / (Price, quantity)."""
    if isinstance(items, (Price, tuple)):
        items = [items]
    normalized = [item if isinstance(item, tuple) else (item, 1) for item in items]
    sub = subscriptions.create_subscription(customer, normalized, **kwargs)
    db.session.flush()
    return sub


def invoice_item(customer, amount, description="One-off charge", currency=None, subscription=None):
    currency = currency or customer.currency or "eur"
    if customer.currency is None:
        customer.currency = currency
    obj = InvoiceItem(
        tenant_id=customer.tenant_id,
        customer=customer,
        subscription=subscription,
        amount=amount,
        currency=currency,
        description=description,
    )
    db.session.add(obj)
    db.session.flush()
    return obj
