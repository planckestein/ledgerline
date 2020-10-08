from datetime import timedelta

from ledgerline.api.idempotency import purge_expired
from ledgerline.models import Customer, IdempotencyKey


def test_replays_the_first_response(api):
    first = api.post("/v1/customers", json={"email": "a@example.com"}, idempotency_key="key-1")
    second = api.post("/v1/customers", json={"email": "a@example.com"}, idempotency_key="key-1")
    assert first.status_code == second.status_code == 201
    assert first.get_json() == second.get_json()
    assert "Idempotent-Replayed" not in first.headers
    assert second.headers["Idempotent-Replayed"] == "true"
    assert Customer.query.count() == 1


def test_parameter_order_does_not_matter(api):
    api.post("/v1/customers", json={"email": "a@example.com", "name": "A"}, idempotency_key="k")
    response = api.client.post(
        "/v1/customers",
        data='{"name": "A",   "email": "a@example.com"}',
        content_type="application/json",
        headers=api._headers("k"),
    )
    assert response.headers.get("Idempotent-Replayed") == "true"


def test_reusing_a_key_with_different_parameters_is_rejected(api):
    api.post("/v1/customers", json={"email": "a@example.com"}, idempotency_key="key-1")
    response = api.post("/v1/customers", json={"email": "b@example.com"}, idempotency_key="key-1")
    assert response.status_code == 422
    assert response.get_json()["error"]["type"] == "idempotency_error"
    assert Customer.query.count() == 1


def test_reusing_a_key_on_another_endpoint_is_rejected(api):
    api.post("/v1/customers", json={}, idempotency_key="key-1")
    response = api.post("/v1/products", json={}, idempotency_key="key-1")
    assert response.status_code == 422


def test_client_errors_are_stored_and_replayed(api):
    first = api.post("/v1/customers", json={"email": "bad"}, idempotency_key="key-2")
    second = api.post("/v1/customers", json={"email": "bad"}, idempotency_key="key-2")
    assert first.status_code == second.status_code == 400
    assert second.headers["Idempotent-Replayed"] == "true"


def test_keys_expire(api, clock):
    api.post("/v1/customers", json={}, idempotency_key="key-3")
    clock.advance(hours=24, seconds=1)
    response = api.post("/v1/customers", json={}, idempotency_key="key-3")
    assert response.status_code == 201
    assert "Idempotent-Replayed" not in response.headers
    assert Customer.query.count() == 2


def test_in_flight_keys_conflict(db, api, tenant):
    db.session.add(
        IdempotencyKey(
            tenant_id=tenant.id,
            key="busy",
            request_method="POST",
            request_path="/v1/customers",
            request_fingerprint=_fingerprint_of(api, {}),
        )
    )
    db.session.commit()
    response = api.post("/v1/customers", json={}, idempotency_key="busy")
    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "idempotency_key_in_use"


def _fingerprint_of(api, body):
    """Compute the fingerprint the server would compute for POST /v1/customers."""
    import json

    from flask import current_app

    from ledgerline.api.idempotency import request_fingerprint

    with current_app.test_request_context(
        "/v1/customers", method="POST", data=json.dumps(body), content_type="application/json"
    ):
        return request_fingerprint()


def test_key_length_is_validated(api):
    response = api.post("/v1/customers", json={}, idempotency_key="x" * 256)
    assert response.status_code == 400
    assert response.get_json()["error"]["param"] == "Idempotency-Key"


def test_requests_without_a_key_are_not_recorded(api):
    api.post("/v1/customers", json={})
    assert IdempotencyKey.query.count() == 0


def test_purge_expired(db, api, clock):
    api.post("/v1/customers", json={}, idempotency_key="old")
    clock.advance(hours=25)
    api.post("/v1/customers", json={}, idempotency_key="new")
    assert purge_expired(clock.now() + timedelta(seconds=1)) == 1
    assert [k.key for k in IdempotencyKey.query.all()] == ["new"]
