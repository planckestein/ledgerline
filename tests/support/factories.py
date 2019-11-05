"""Factories that build valid domain objects through the service layer.

They flush but never commit; tests decide when a transaction ends.
"""
import itertools

from ledgerline.extensions import db
from ledgerline.geo import serialize_address
from ledgerline.models import ApiKey, Customer, Tenant

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
    return obj
