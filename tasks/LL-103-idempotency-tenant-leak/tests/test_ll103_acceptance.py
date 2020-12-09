"""LL-103 acceptance tests: idempotency keys are scoped per tenant, in code and in the schema."""
import io
import os
from datetime import datetime

from sqlalchemy import inspect, text

from ledgerline.extensions import db as _db
from ledgerline.models import Customer, IdempotencyKey
from tests.support import factories
from tests.support.migrations import downgrade, migration_app, schema_diff, upgrade

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
V141_HEAD = "f3b9d2e6a399"


def unique_column_sets(table):
    inspector = inspect(_db.engine)
    sets = [frozenset(c["column_names"]) for c in inspector.get_unique_constraints(table)]
    sets += [frozenset(i["column_names"]) for i in inspector.get_indexes(table) if i["unique"]]
    return sets


class TestApiBehaviour:
    def test_same_key_and_body_in_two_tenants(self, api, other_api):
        body = {"email": "buyer@example.com"}
        first = api.post("/v1/customers", json=body, idempotency_key="order-1001")
        second = other_api.post("/v1/customers", json=body, idempotency_key="order-1001")
        assert first.status_code == second.status_code == 201
        assert "Idempotent-Replayed" not in second.headers
        assert second.get_json()["id"] != first.get_json()["id"]
        assert other_api.get("/v1/customers/%s" % second.get_json()["id"]).status_code == 200
        assert api.get("/v1/customers/%s" % second.get_json()["id"]).status_code == 404
        assert other_api.get("/v1/customers/%s" % first.get_json()["id"]).status_code == 404
        assert Customer.query.count() == 2

    def test_same_key_different_body_in_two_tenants(self, api, other_api):
        api.post("/v1/customers", json={"email": "a@example.com"}, idempotency_key="order-7")
        response = other_api.post(
            "/v1/customers", json={"email": "b@example.com"}, idempotency_key="order-7"
        )
        assert response.status_code == 201
        assert response.get_json()["email"] == "b@example.com"

    def test_each_tenant_replays_its_own_response(self, api, other_api):
        mine = api.post("/v1/products", json={"name": "A"}, idempotency_key="k").get_json()
        theirs = other_api.post("/v1/products", json={"name": "A"}, idempotency_key="k").get_json()
        replay_mine = api.post("/v1/products", json={"name": "A"}, idempotency_key="k")
        replay_theirs = other_api.post("/v1/products", json={"name": "A"}, idempotency_key="k")
        assert theirs["id"] != mine["id"]
        assert replay_mine.get_json() == mine
        assert replay_theirs.get_json() == theirs
        assert replay_mine.headers["Idempotent-Replayed"] == "true"
        assert replay_theirs.headers["Idempotent-Replayed"] == "true"

    def test_single_tenant_semantics_are_unchanged(self, api):
        api.post("/v1/customers", json={"email": "a@example.com"}, idempotency_key="x")
        assert (
            api.post("/v1/customers", json={"email": "b@example.com"}, idempotency_key="x")
        ).status_code == 422
        replay = api.post("/v1/customers", json={"email": "a@example.com"}, idempotency_key="x")
        assert replay.headers["Idempotent-Replayed"] == "true"

    def test_lookups_still_use_the_hash(self, api, tenant):
        api.post("/v1/customers", json={}, idempotency_key="hashed-key")
        record = IdempotencyKey.query.filter_by(tenant_id=tenant.id).one()
        assert record.key_hash == IdempotencyKey.hash_key("hashed-key")


class TestDatabaseConstraint:
    def test_two_tenants_may_store_the_same_key(self, db, tenant, other_tenant):
        for owner in (tenant, other_tenant):
            db.session.add(
                IdempotencyKey(
                    tenant_id=owner.id,
                    key="shared",
                    key_hash=IdempotencyKey.hash_key("shared"),
                    request_method="POST",
                    request_path="/v1/customers",
                    request_fingerprint="0" * 64,
                )
            )
        db.session.commit()
        assert IdempotencyKey.query.count() == 2

    def test_one_tenant_may_not_store_a_key_twice(self, db, tenant):
        from sqlalchemy.exc import IntegrityError

        import pytest

        for _ in range(2):
            db.session.add(
                IdempotencyKey(
                    tenant_id=tenant.id,
                    key="dup",
                    key_hash=IdempotencyKey.hash_key("dup"),
                    request_method="POST",
                    request_path="/v1/customers",
                    request_fingerprint="0" * 64,
                )
            )
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


class TestMigration:
    def test_head_enforces_tenant_scoped_uniqueness(self):
        with migration_app() as (app, config):
            upgrade(config, "head")
            sets = unique_column_sets("idempotency_keys")
            assert frozenset(["tenant_id", "key_hash"]) in sets
            assert frozenset(["key_hash"]) not in sets
            assert schema_diff() == []

    def test_existing_rows_survive_upgrade_and_downgrade(self):
        with migration_app() as (app, config):
            upgrade(config, V141_HEAD)
            now = datetime(2020, 10, 1, 12)
            with _db.engine.begin() as connection:
                for tenant_id in (1, 2):
                    connection.execute(
                        text(
                            "INSERT INTO tenants (id, public_id, name, home_country, "
                            "default_currency, dunning_retry_days, dunning_final_action, "
                            "created_at, updated_at) VALUES (:id, :pid, 'T', 'DE', 'eur', "
                            "'3,5,7', 'cancel', :now, :now)"
                        ),
                        id=tenant_id,
                        pid="acct_%d" % tenant_id,
                        now=now,
                    )
                    key = "legacy-%d" % tenant_id
                    connection.execute(
                        text(
                            "INSERT INTO idempotency_keys (tenant_id, key, key_hash, "
                            "request_method, request_path, request_fingerprint, response_status, "
                            "response_body, created_at) VALUES (:tenant, :key, :hash, 'POST', "
                            "'/v1/customers', :fp, 201, '{}', :now)"
                        ),
                        tenant=tenant_id,
                        key=key,
                        hash=IdempotencyKey.hash_key(key),
                        fp="0" * 64,
                        now=now,
                    )

            upgrade(config, "head")
            with _db.engine.begin() as connection:
                rows = connection.execute(
                    text("SELECT tenant_id, key, key_hash FROM idempotency_keys ORDER BY tenant_id")
                ).fetchall()
                assert [(r[0], r[1]) for r in rows] == [(1, "legacy-1"), (2, "legacy-2")]
                assert rows[0][2] == IdempotencyKey.hash_key("legacy-1")
                # The same key in another tenant is now accepted by the database.
                connection.execute(
                    text(
                        "INSERT INTO idempotency_keys (tenant_id, key, key_hash, request_method, "
                        "request_path, request_fingerprint, created_at) VALUES (2, 'legacy-1', "
                        ":hash, 'POST', '/v1/customers', :fp, :now)"
                    ),
                    hash=IdempotencyKey.hash_key("legacy-1"),
                    fp="0" * 64,
                    now=now,
                )
                connection.execute(text("DELETE FROM idempotency_keys WHERE id = 3"))

            downgrade(config, V141_HEAD)
            upgrade(config, "head")
            with _db.engine.begin() as connection:
                count = connection.execute(text("SELECT COUNT(*) FROM idempotency_keys")).scalar()
            assert count == 2


def test_changelog_mentions_the_fix():
    with io.open(os.path.join(REPO, "CHANGELOG.md"), encoding="utf-8") as handle:
        changelog = handle.read()
    head, _, _ = changelog.partition("## 1.4.1")
    assert "## Unreleased" in head
    assert "dempotency" in head.split("## Unreleased", 1)[1]
