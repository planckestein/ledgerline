"""LL-107 acceptance tests: structured addresses and tax IDs (migration + application)."""
import io
import json
import os
import re
from datetime import datetime

from sqlalchemy import inspect, text

from ledgerline.app import MIGRATIONS_DIR
from ledgerline.extensions import db as _db
from tests.support.migrations import downgrade, migration_app, schema_diff, upgrade

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURE = os.path.join(os.path.dirname(HERE), "fixtures", "legacy_customers.json")
V141_HEAD = "f3b9d2e6a399"
ADDRESS_FIELDS = ("line1", "line2", "city", "state", "postal_code", "country")
ORIGINAL_REVISIONS = {
    "1c8e2f3a9b10",
    "4a7d9e1c2b33",
    "7b2f5c8d1e44",
    "9e3a1d6f7c55",
    "b5c8e2a4f066",
    "d2f6a9b3c177",
    "e8a1c4d7b288",
    "f3b9d2e6a399",
}
NOW = datetime(2020, 10, 1, 12)


def load_fixture():
    with io.open(FIXTURE, encoding="utf-8") as handle:
        return json.load(handle)


def seed_legacy_rows(connection, rows):
    connection.execute(
        text(
            "INSERT INTO tenants (id, public_id, name, home_country, default_currency, "
            "dunning_retry_days, dunning_final_action, created_at, updated_at) "
            "VALUES (1, 'acct_1', 'T', 'DE', 'eur', '3,5,7', 'cancel', :now, :now)"
        ),
        now=NOW,
    )
    for row in rows:
        connection.execute(
            text(
                "INSERT INTO customers (id, public_id, tenant_id, billing_address, vat_id, "
                "tax_exempt, invoice_prefix, next_invoice_sequence, created_at, updated_at) "
                "VALUES (:id, :pid, 1, :address, :vat, :exempt, :prefix, 1, :now, :now)"
            ),
            id=row["id"],
            pid="cus_%d" % row["id"],
            address=row["billing_address"],
            vat=row["vat_id"],
            exempt=False,
            prefix="P%07d" % row["id"],
            now=NOW,
        )


class TestDataMigration:
    def test_upgrade_converts_every_legacy_format(self):
        rows = load_fixture()
        with migration_app() as (app, config):
            upgrade(config, V141_HEAD)
            with _db.engine.begin() as connection:
                seed_legacy_rows(connection, rows)
            upgrade(config, "head")

            columns = {c["name"] for c in inspect(_db.engine).get_columns("customers")}
            assert "billing_address" not in columns
            assert "vat_id" not in columns
            assert {"address_%s" % f for f in ADDRESS_FIELDS} <= columns

            with _db.engine.begin() as connection:
                for row in rows:
                    stored = connection.execute(
                        text(
                            "SELECT address_line1, address_line2, address_city, address_state, "
                            "address_postal_code, address_country FROM customers WHERE id = :id"
                        ),
                        id=row["id"],
                    ).fetchone()
                    assert dict(zip(ADDRESS_FIELDS, stored)) == row["expected_address"], row
                    tax_ids = connection.execute(
                        text(
                            "SELECT type, value, tenant_id, public_id FROM customer_tax_ids "
                            "WHERE customer_id = :id ORDER BY id"
                        ),
                        id=row["id"],
                    ).fetchall()
                    assert [{"type": t[0], "value": t[1]} for t in tax_ids] == row[
                        "expected_tax_ids"
                    ], row
                    assert all(t[2] == 1 and t[3].startswith("txi_") for t in tax_ids)
            assert schema_diff() == []

    def test_downgrade_restores_legacy_columns(self):
        rows = load_fixture()
        with migration_app() as (app, config):
            upgrade(config, V141_HEAD)
            with _db.engine.begin() as connection:
                seed_legacy_rows(connection, rows)
            upgrade(config, "head")
            downgrade(config, V141_HEAD)
            with _db.engine.begin() as connection:
                for row in rows:
                    address, vat = connection.execute(
                        text("SELECT billing_address, vat_id FROM customers WHERE id = :id"),
                        id=row["id"],
                    ).fetchone()
                    expected = {k: v for k, v in row["expected_address"].items() if v}
                    if expected:
                        assert json.loads(address) == expected, row
                        assert address == json.dumps(expected, sort_keys=True), row
                    else:
                        assert address is None, row
                    tax_ids = row["expected_tax_ids"]
                    assert vat == (tax_ids[0]["value"] if tax_ids else None), row
            assert "customer_tax_ids" not in inspect(_db.engine).get_table_names()

    def test_new_migrations_are_self_contained(self):
        versions = os.path.join(MIGRATIONS_DIR, "versions")
        new_files = [
            name
            for name in os.listdir(versions)
            if name.endswith(".py") and name.split("_", 1)[0] not in ORIGINAL_REVISIONS
        ]
        assert new_files, "no new migration found"
        for name in new_files:
            with io.open(os.path.join(versions, name), encoding="utf-8") as handle:
                source = handle.read()
            imports = re.findall(r"^\s*(?:from|import)\s+(ledgerline\S*)", source, re.M)
            assert imports == [], "%s imports application code: %s" % (name, imports)
            assert "import_module" not in source and "__import__" not in source, name


def create_customer(api, **body):
    response = api.post("/v1/customers", json=body)
    assert response.status_code == 201, response.get_json()
    return response.get_json()


class TestApplication:
    def test_api_round_trip(self, api):
        customer = create_customer(
            api,
            address={"line1": "Ermou 2", "city": "Athens", "country": "gr"},
            vat_id="el 094.259.216",
        )
        assert customer["address"] == {
            "line1": "Ermou 2",
            "line2": None,
            "city": "Athens",
            "state": None,
            "postal_code": None,
            "country": "GR",
        }
        assert customer["vat_id"] == "EL094259216"
        [tax_id] = customer["tax_ids"]
        assert tax_id["id"].startswith("txi_")
        assert (tax_id["type"], tax_id["value"]) == ("eu_vat", "EL094259216")
        row = _db.session.execute(
            text("SELECT address_city, address_country FROM customers")
        ).fetchone()
        assert tuple(row) == ("Athens", "GR")

    def test_updating_vat_id_replaces_tax_ids(self, api):
        customer = create_customer(api, vat_id="DE811907980")
        url = "/v1/customers/%s" % customer["id"]
        updated = api.post(url, json={"vat_id": "GB980780684"}).get_json()
        assert [(t["type"], t["value"]) for t in updated["tax_ids"]] == [("gb_vat", "GB980780684")]
        cleared = api.post(url, json={"vat_id": None}).get_json()
        assert (cleared["vat_id"], cleared["tax_ids"]) == (None, [])
        cleared = api.post(url, json={"vat_id": "DE1"}).get_json()
        cleared = api.post(url, json={"vat_id": "  "}).get_json()
        assert cleared["tax_ids"] == []

    def test_partial_update_keeps_other_fields(self, api):
        customer = create_customer(api, address={"country": "FR", "city": "Lyon"}, vat_id="FR1")
        updated = api.post("/v1/customers/%s" % customer["id"], json={"name": "N"}).get_json()
        assert updated["address"]["city"] == "Lyon"
        assert updated["vat_id"] == "FR1"

    def test_import_accepts_vat_ids(self, api):
        response = api.post(
            "/v1/customers/import",
            json={"customers": [{"vat_id": "CHE-123.456.789"}, {"address": {"country": "us"}}]},
        )
        first, second = response.get_json()["data"]
        assert [(t["type"], t["value"]) for t in first["tax_ids"]] == [("ch_vat", "CHE123456789")]
        assert second["address"]["country"] == "US" and second["tax_ids"] == []

    def _invoice_tax(self, api, customer):
        api.post(
            "/v1/invoiceitems",
            json={"customer": customer["id"], "amount": 1000, "currency": "eur", "description": "x"},
        )
        return api.post("/v1/invoices", json={"customer": customer["id"]}).get_json()["tax_total"]

    def test_reverse_charge_requires_an_eu_vat_id(self, api):
        api.post("/v1/tax_rates", json={"display_name": "FR", "percentage": "20", "country": "FR"})
        eu = create_customer(api, address={"country": "FR"}, vat_id="FR40303265045")
        foreign = create_customer(api, address={"country": "FR"}, vat_id="GB980780684")
        none = create_customer(api, address={"country": "FR"})
        assert self._invoice_tax(api, eu) == 0
        assert self._invoice_tax(api, foreign) == 200
        assert self._invoice_tax(api, none) == 200

    def test_tax_uses_structured_state(self, api):
        api.post(
            "/v1/tax_rates",
            json={"display_name": "CA", "percentage": "7.25", "country": "US", "state": "CA"},
        )
        customer = create_customer(api, address={"country": "US", "state": "CA"})
        assert self._invoice_tax(api, customer) == 73
