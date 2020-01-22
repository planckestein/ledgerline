from ledgerline import clock
from ledgerline.models import ApiKey


class TestAuthentication:
    def test_missing_key(self, app, tenant):
        response = app.test_client().get("/v1/customers")
        assert response.status_code == 401
        assert response.get_json()["error"]["code"] == "missing_api_key"

    def test_invalid_key(self, app, tenant):
        response = app.test_client().get(
            "/v1/customers", headers={"Authorization": "Bearer sk_test_nope"}
        )
        assert response.status_code == 401
        assert response.get_json()["error"]["type"] == "authentication_error"

    def test_revoked_key(self, db, api):
        key = ApiKey.query.filter_by(key_hash=ApiKey.hash_secret(api.secret)).one()
        key.revoked_at = clock.utcnow()
        db.session.commit()
        assert api.get("/v1/customers").status_code == 401

    def test_health_needs_no_key(self, app):
        assert app.test_client().get("/health").get_json()["status"] == "ok"

    def test_tenants_cannot_see_each_other(self, api, other_api):
        customer = api.post("/v1/customers", json={"email": "a@example.com"}).get_json()
        response = other_api.get("/v1/customers/%s" % customer["id"])
        assert response.status_code == 404
        assert response.get_json()["error"]["code"] == "resource_missing"
        assert other_api.get("/v1/customers").get_json()["data"] == []


class TestCustomers:
    def test_create_and_fetch(self, api):
        response = api.post(
            "/v1/customers",
            json={
                "email": "jane@example.com",
                "name": "Jane",
                "address": {"line1": "Unter den Linden 1", "city": "Berlin", "country": "de"},
                "metadata": {"crm_id": "42"},
            },
        )
        assert response.status_code == 201
        body = response.get_json()
        assert body["id"].startswith("cus_")
        assert body["address"]["country"] == "DE"
        assert body["address"]["city"] == "Berlin"
        assert body["metadata"] == {"crm_id": "42"}
        assert body["currency"] is None
        assert len(body["invoice_prefix"]) == 8

        fetched = api.get("/v1/customers/%s" % body["id"]).get_json()
        assert fetched == body

    def test_update(self, api):
        customer = api.post("/v1/customers", json={"email": "a@example.com"}).get_json()
        response = api.post("/v1/customers/%s" % customer["id"], json={"name": "Renamed"})
        assert response.status_code == 200
        assert response.get_json()["name"] == "Renamed"
        assert response.get_json()["email"] == "a@example.com"

    def test_validation_errors_name_the_parameter(self, api):
        response = api.post("/v1/customers", json={"email": "not-an-email"})
        assert response.status_code == 400
        error = response.get_json()["error"]
        assert error["type"] == "invalid_request_error"
        assert error["param"] == "email"

        response = api.post("/v1/customers", json={"address": {"country": "Germany"}})
        assert response.get_json()["error"]["param"] == "address.country"

        response = api.post("/v1/customers", json={"emial": "typo@example.com"})
        assert response.get_json()["error"]["param"] == "emial"

    def test_body_must_be_an_object(self, api):
        response = api.client.post(
            "/v1/customers",
            data="[1, 2]",
            content_type="application/json",
            headers=api._headers(),
        )
        assert response.status_code == 400

    def test_filter_by_email(self, api, clock):
        api.post("/v1/customers", json={"email": "a@example.com"})
        clock.advance(seconds=1)
        api.post("/v1/customers", json={"email": "b@example.com"})
        data = api.get("/v1/customers", email="b@example.com").get_json()["data"]
        assert [c["email"] for c in data] == ["b@example.com"]

    def test_payment_methods(self, api):
        customer = api.post("/v1/customers", json={}).get_json()
        response = api.post(
            "/v1/customers/%s/payment_methods" % customer["id"], json={"token": "tok_visa"}
        )
        assert response.status_code == 201
        method = response.get_json()
        assert method["card"] == {"brand": "visa", "last4": "4242"}
        assert method["is_default"] is True
        fetched = api.get("/v1/customers/%s" % customer["id"]).get_json()
        assert fetched["default_payment_method"] == method["id"]

        bad = api.post("/v1/customers/%s/payment_methods" % customer["id"], json={"token": "x"})
        assert bad.status_code == 400
        assert bad.get_json()["error"]["code"] == "invalid_token"

    def test_unknown_route_is_json(self, api):
        response = api.get("/v1/nope")
        assert response.status_code == 404
        assert response.get_json()["error"]["type"] == "invalid_request_error"
