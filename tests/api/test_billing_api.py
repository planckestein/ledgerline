"""End-to-end flows through the public API."""
from datetime import datetime


def create_customer(api, token="tok_visa", **fields):
    customer = api.post("/v1/customers", json=fields).get_json()
    if token:
        api.post("/v1/customers/%s/payment_methods" % customer["id"], json={"token": token})
    return customer


def create_price(api, **fields):
    product = api.post("/v1/products", json={"name": "Pro"}).get_json()
    body = {
        "product": product["id"],
        "currency": "eur",
        "unit_amount": 1000,
        "recurring": {"interval": "month"},
    }
    body.update(fields)
    response = api.post("/v1/prices", json=body)
    assert response.status_code == 201, response.get_json()
    return response.get_json()


class TestCatalog:
    def test_price_defaults(self, api):
        price = create_price(api)
        assert price["billing_scheme"] == "per_unit"
        assert price["recurring"] == {
            "interval": "month",
            "interval_count": 1,
        }

    def test_price_validation(self, api):
        product = api.post("/v1/products", json={"name": "Pro"}).get_json()
        base = {"product": product["id"], "currency": "eur", "unit_amount": 1000}
        cases = [
            (
                dict(base, recurring={"interval": "month", "interval_count": 13}),
                "recurring.interval_count",
            ),
            (dict(base, currency="xxx", recurring={"interval": "month"}), "currency"),
            (dict(base, unit_amount=-1, recurring={"interval": "month"}), "unit_amount"),
            (dict(base, billing_scheme="package", recurring={"interval": "month"}), "package_size"),
            (dict(base, product="prod_missing", recurring={"interval": "month"}), "product"),
        ]
        for body, param in cases:
            response = api.post("/v1/prices", json=body)
            assert response.status_code in (400, 404), body
            assert response.get_json()["error"]["param"] == param, body

    def test_deactivate_price(self, api):
        price = create_price(api)
        response = api.post("/v1/prices/%s" % price["id"], json={"active": False})
        assert response.get_json()["active"] is False
        listed = api.get("/v1/prices", active="true").get_json()["data"]
        assert listed == []


class TestSubscriptions:
    def test_create_update_and_cancel(self, api, clock):
        customer = create_customer(api)
        price = create_price(api)
        response = api.post(
            "/v1/subscriptions",
            json={"customer": customer["id"], "items": [{"price": price["id"], "quantity": 2}]},
        )
        assert response.status_code == 201, response.get_json()
        sub = response.get_json()
        assert sub["status"] == "active"
        assert sub["items"]["data"][0]["quantity"] == 2
        assert sub["current_period_end"] - sub["current_period_start"] == 30 * 86400

        clock.set(datetime(2020, 6, 16, 12))
        updated = api.post(
            "/v1/subscriptions/%s" % sub["id"],
            json={"items": [{"price": price["id"], "quantity": 1}], "cancel_at_period_end": True},
        ).get_json()
        assert updated["cancel_at_period_end"] is True

        canceled = api.post("/v1/subscriptions/%s/cancel" % sub["id"], json={}).get_json()
        assert canceled["status"] == "canceled"
        again = api.post("/v1/subscriptions/%s/cancel" % sub["id"], json={})
        assert again.status_code == 409

    def test_errors(self, api):
        customer = create_customer(api, token=None)
        price = create_price(api)
        response = api.post(
            "/v1/subscriptions",
            json={"customer": customer["id"], "items": [{"price": price["id"]}]},
        )
        assert response.status_code == 400
        assert response.get_json()["error"]["code"] == "missing_payment_method"

        response = api.post("/v1/subscriptions", json={"customer": customer["id"], "items": []})
        assert response.get_json()["error"]["param"] == "items"

        response = api.post(
            "/v1/subscriptions", json={"customer": customer["id"], "items": [{"price": "price_x"}]}
        )
        assert response.status_code == 404
