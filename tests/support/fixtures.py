"""Pytest fixtures shared by every test suite."""
import datetime
import json as jsonlib

import pytest

from ledgerline.app import create_app
from ledgerline.clock import FrozenClock, set_clock
from ledgerline.extensions import db as _db
from tests.support import factories

# Every test starts at the same, boring instant unless it moves the clock.
START = datetime.datetime(2020, 6, 1, 12, 0, 0)


@pytest.fixture(autouse=True)
def clock():
    frozen = FrozenClock(START)
    previous = set_clock(frozen)
    yield frozen
    set_clock(previous)


@pytest.fixture
def app():
    app = create_app("testing")
    with app.app_context():
        _db.create_all()
        yield app
        _db.session.remove()
        _db.drop_all()


@pytest.fixture
def db(app):
    return _db


@pytest.fixture
def tenant(db):
    tenant = factories.tenant()
    db.session.commit()
    return tenant


@pytest.fixture
def other_tenant(db):
    tenant = factories.tenant(name="Globex Ltd", home_country="GB", default_currency="gbp")
    db.session.commit()
    return tenant


class ApiClient:
    """Thin wrapper around Flask's test client that authenticates as one tenant."""

    def __init__(self, client, secret):
        self.client = client
        self.secret = secret

    def _headers(self, idempotency_key=None, headers=None):
        result = {"Authorization": "Bearer %s" % self.secret}
        if idempotency_key is not None:
            result["Idempotency-Key"] = idempotency_key
        result.update(headers or {})
        return result

    def get(self, path, headers=None, **params):
        return self.client.get(path, query_string=params, headers=self._headers(headers=headers))

    def post(self, path, json=None, idempotency_key=None, headers=None):
        body = jsonlib.dumps(json) if json is not None else ""
        return self.client.post(
            path,
            data=body,
            content_type="application/json",
            headers=self._headers(idempotency_key, headers),
        )


@pytest.fixture
def api(app, tenant):
    secret = factories.api_key(tenant)
    _db.session.commit()
    return ApiClient(app.test_client(), secret)


@pytest.fixture
def other_api(app, other_tenant):
    secret = factories.api_key(other_tenant)
    _db.session.commit()
    return ApiClient(app.test_client(), secret)
