"""LL-104 acceptance tests: stable cursor pagination and constant-query list endpoints."""
import contextlib
from datetime import datetime

import pytest
from sqlalchemy import event

from ledgerline.billing.renewal import run_billing_cycle
from ledgerline.extensions import db as _db
from tests.support import factories


@contextlib.contextmanager
def count_statements():
    statements = []

    def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    engine = _db.engine
    event.listen(engine, "before_cursor_execute", before_cursor_execute)
    try:
        yield statements
    finally:
        event.remove(engine, "before_cursor_execute", before_cursor_execute)


def import_customers(api, count, prefix="c"):
    response = api.post(
        "/v1/customers/import",
        json={"customers": [{"name": "%s%02d" % (prefix, i)} for i in range(count)]},
    )
    assert response.status_code == 201
    return [c["id"] for c in response.get_json()["data"]]


def walk_forward(api, path, limit, **params):
    pages, cursor = [], None
    while True:
        query = dict(params, limit=limit)
        if cursor:
            query["starting_after"] = cursor
        page = api.get(path, **query).get_json()
        pages.append(page)
        if not page["has_more"]:
            return pages
        cursor = page["data"][-1]["id"]
        assert len(pages) < 50, "pagination does not terminate"


def walk_backward(api, path, limit, start_before):
    pages, cursor = [], start_before
    while True:
        page = api.get(path, limit=limit, ending_before=cursor).get_json()
        pages.append(page)
        if not page["has_more"]:
            return pages
        cursor = page["data"][0]["id"]
        assert len(pages) < 50, "pagination does not terminate"


def ids(pages):
    return [obj["id"] for page in pages for obj in page["data"]]


class TestCursorPagination:
    def test_bulk_import_is_paged_exactly_once(self, api):
        imported = import_customers(api, 25)
        pages = walk_forward(api, "/v1/customers", 10)
        assert [len(p["data"]) for p in pages] == [10, 10, 5]
        assert [p["has_more"] for p in pages] == [True, True, False]
        assert sorted(ids(pages)) == sorted(imported)

    def test_order_is_newest_first_then_by_id(self, api, clock):
        first_batch = import_customers(api, 3, "a")
        clock.advance(seconds=5)
        single = api.post("/v1/customers", json={"name": "single"}).get_json()["id"]
        clock.advance(seconds=5)
        second_batch = import_customers(api, 3, "b")
        listed = ids(walk_forward(api, "/v1/customers", 2))
        assert listed == list(reversed(first_batch + [single] + second_batch))

    def test_ending_before_walks_back_without_duplicates(self, api):
        imported = import_customers(api, 12)
        forward = ids(walk_forward(api, "/v1/customers", 5))
        last = forward[-1]
        backward = walk_backward(api, "/v1/customers", 5, last)
        collected = []
        for page in backward:
            collected = [obj["id"] for obj in page["data"]] + collected
        assert collected == forward[:-1]
        assert sorted(forward) == sorted(imported)

    def test_ending_before_page_contents(self, api):
        imported = import_customers(api, 6)
        listed = ids(walk_forward(api, "/v1/customers", 100))
        assert sorted(listed) == sorted(imported)
        page = api.get("/v1/customers", limit=2, ending_before=listed[4]).get_json()
        assert [c["id"] for c in page["data"]] == listed[2:4]
        assert page["has_more"] is True
        page = api.get("/v1/customers", limit=2, ending_before=listed[2]).get_json()
        assert [c["id"] for c in page["data"]] == listed[0:2]
        assert page["has_more"] is False

    def test_has_more_is_false_on_an_exact_multiple(self, api, clock):
        for index in range(20):
            api.post("/v1/products", json={"name": "p%d" % index})
            clock.advance(seconds=1)
        pages = walk_forward(api, "/v1/products", 10)
        assert [p["has_more"] for p in pages] == [True, False]
        assert len(set(ids(pages))) == 20

    def test_has_more_on_a_single_full_page(self, api):
        import_customers(api, 3)
        page = api.get("/v1/customers", limit=3).get_json()
        assert len(page["data"]) == 3
        assert page["has_more"] is False

    def test_invoices_created_in_the_same_instant(self, api, tenant):
        price = factories.price(tenant)
        for _ in range(9):
            factories.subscribe(factories.customer(tenant), price)
        _db.session.commit()
        pages = walk_forward(api, "/v1/invoices", 4)
        assert [len(p["data"]) for p in pages] == [4, 4, 1]
        assert len(set(ids(pages))) == 9

    def test_events_are_paged_exactly_once(self, api):
        import_customers(api, 15)
        pages = walk_forward(api, "/v1/events", 4, type="customer.created")
        assert len(ids(pages)) == len(set(ids(pages))) == 15


@pytest.fixture
def busy_tenant(db, tenant, clock):
    """10 customers x 3-item subscriptions renewed twice: 30 invoices of 3 lines each."""
    factories.tax_rate(tenant, "19", country="DE")
    coupon = factories.coupon(tenant, percent_off=10)
    prices = [factories.price(tenant, unit_amount=1000 * (i + 1)) for i in range(3)]
    for index in range(10):
        factories.subscribe(
            factories.customer(tenant), prices, coupon=coupon if index % 2 else None
        )
    for moment in (datetime(2020, 7, 1, 12), datetime(2020, 8, 1, 12)):
        clock.set(moment)
        run_billing_cycle()
    db.session.commit()
    db.session.remove()
    return tenant


class TestQueryCounts:
    def test_invoice_list(self, api, busy_tenant):
        with count_statements() as statements:
            response = api.get("/v1/invoices", limit=100)
        body = response.get_json()
        assert len(body["data"]) == 30
        assert all(len(invoice["lines"]["data"]) == 3 for invoice in body["data"])
        assert all(line["price"] and line["tax_rate"] for i in body["data"] for line in i["lines"]["data"])
        assert sum(1 for invoice in body["data"] if invoice["coupon"]) == 15
        assert len(statements) <= 10, "\n\n".join(statements)

    def test_subscription_list(self, api, busy_tenant):
        with count_statements() as statements:
            response = api.get("/v1/subscriptions", limit=100)
        body = response.get_json()
        assert len(body["data"]) == 10
        assert all(len(sub["items"]["data"]) == 3 for sub in body["data"])
        assert len(statements) <= 8, "\n\n".join(statements)

    def test_customer_list(self, api, busy_tenant):
        with count_statements() as statements:
            response = api.get("/v1/customers", limit=100)
        body = response.get_json()
        assert len(body["data"]) == 10
        assert all(customer["default_payment_method"] for customer in body["data"])
        assert len(statements) <= 5, "\n\n".join(statements)

    def test_query_count_does_not_grow_with_page_size(self, api, busy_tenant):
        with count_statements() as small:
            api.get("/v1/invoices", limit=2)
        with count_statements() as large:
            api.get("/v1/invoices", limit=100)
        assert len(large) == len(small)
