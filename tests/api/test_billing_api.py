"""End-to-end flows through the public API."""


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
