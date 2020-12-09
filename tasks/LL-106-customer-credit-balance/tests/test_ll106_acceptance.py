"""LL-106 acceptance tests: customer credit balances."""
from datetime import datetime

from sqlalchemy import inspect, text

from ledgerline.billing import invoicing
from ledgerline.billing import subscriptions as service
from ledgerline.billing.renewal import run_billing_cycle
from ledgerline.extensions import db as _db
from ledgerline.ledger import reports
from ledgerline.models import Customer, Invoice, PaymentAttempt
from tests.support import factories
from tests.support.migrations import downgrade, migration_app, schema_diff, upgrade

V141_HEAD = "f3b9d2e6a399"
CREDIT = "2200_customer_credit"
ADJUSTMENTS = "4900_credit_adjustments"
RECEIVABLE = "1100_accounts_receivable"
JUN_16 = datetime(2020, 6, 16, 12)
JUL_1 = datetime(2020, 7, 1, 12)


def balances(tenant, currency="eur"):
    return reports.account_balances(tenant.id, currency)


def assert_ledger_consistent(tenant, currency="eur"):
    assert reports.trial_balance(tenant.id, currency)["balanced"] is True
    customer_total = sum(
        c.balance for c in Customer.query.filter_by(tenant_id=tenant.id, currency=currency)
    )
    assert balances(tenant, currency).get(CREDIT, 0) == customer_total
    open_due = sum(
        i.amount_due
        for i in Invoice.query.filter_by(tenant_id=tenant.id, currency=currency, status="open")
    )
    assert balances(tenant, currency).get(RECEIVABLE, 0) == open_due


def latest_invoice(sub):
    return Invoice.query.filter_by(subscription_id=sub.id).order_by(Invoice.id.desc()).first()


def grant_credit(api, customer_id, amount, currency="eur"):
    response = api.post(
        "/v1/customers/%s/balance_transactions" % customer_id,
        json={"amount": amount, "currency": currency, "description": "Goodwill"},
    )
    assert response.status_code == 201, response.get_json()
    return response.get_json()


class TestNegativeInvoicesBecomeCredit:
    def test_downgrade_with_always_invoice(self, tenant, clock, gateway):
        customer = factories.customer(tenant)
        price = factories.price(tenant, unit_amount=1000)
        sub = factories.subscribe(customer, [(price, 3)])
        charges = len(gateway.charges)

        clock.set(JUN_16)
        service.update_subscription_items(sub, [(price, 1)], proration_behavior="always_invoice")
        credit_note = latest_invoice(sub)
        assert credit_note.total == -1000
        assert credit_note.status == "paid"
        assert credit_note.amount_due == 0
        assert credit_note.number is not None
        assert (credit_note.starting_balance, credit_note.ending_balance) == (0, -1000)
        assert customer.balance == -1000
        assert len(gateway.charges) == charges
        assert_ledger_consistent(tenant)

        clock.set(JUL_1)
        run_billing_cycle()
        renewal = latest_invoice(sub)
        assert renewal.total == 1000
        assert renewal.amount_due == 0
        assert renewal.amount_paid == 0
        assert renewal.status == "paid"
        assert (renewal.starting_balance, renewal.ending_balance) == (-1000, 0)
        assert PaymentAttempt.query.filter_by(invoice_id=renewal.id).count() == 0
        assert len(gateway.charges) == charges
        assert customer.balance == 0
        assert_ledger_consistent(tenant)

    def test_manual_negative_invoice(self, tenant):
        customer = factories.customer(tenant)
        factories.invoice_item(customer, 300)
        factories.invoice_item(customer, -800)
        invoice = invoicing.create_manual_invoice(customer)
        invoicing.finalize_invoice(invoice)
        assert (invoice.status, invoice.total, invoice.amount_due) == ("paid", -500, 0)
        assert customer.balance == -500
        assert_ledger_consistent(tenant)

    def test_cancel_with_proration_and_invoice_now(self, tenant, clock):
        customer = factories.customer(tenant)
        sub = factories.subscribe(customer, factories.price(tenant, unit_amount=1000))
        clock.set(JUN_16)
        service.cancel_subscription(sub, prorate=True, invoice_now=True)
        final = latest_invoice(sub)
        assert final.billing_reason == "subscription_cancel"
        assert (final.total, final.status) == (-500, "paid")
        assert customer.balance == -500
        assert_ledger_consistent(tenant)


class TestCreditIsConsumed:
    def test_partial_application_charges_the_rest(self, api, tenant, clock, gateway):
        customer = factories.customer(tenant)
        sub = factories.subscribe(customer, factories.price(tenant, unit_amount=1000))
        _db.session.commit()
        grant_credit(api, customer.public_id, -300)

        clock.set(JUL_1)
        run_billing_cycle()
        renewal = latest_invoice(sub)
        assert (renewal.total, renewal.status, renewal.amount_paid) == (1000, "paid", 700)
        assert (renewal.starting_balance, renewal.ending_balance) == (-300, 0)
        assert gateway.charges[-1]["amount"] == 700
        assert [a.amount for a in renewal.payment_attempts] == [700]
        assert_ledger_consistent(tenant)

    def test_credit_larger_than_invoice_carries_over(self, api, tenant, clock):
        customer = factories.customer(tenant)
        sub = factories.subscribe(customer, factories.price(tenant, unit_amount=1000))
        _db.session.commit()
        grant_credit(api, customer.public_id, -2500)
        for moment in (JUL_1, datetime(2020, 8, 1, 12), datetime(2020, 9, 1, 12)):
            clock.set(moment)
            run_billing_cycle()
        renewals = Invoice.query.filter_by(subscription_id=sub.id).order_by(Invoice.id).all()[1:]
        assert [(i.amount_paid, i.ending_balance) for i in renewals] == [
            (0, -1500),
            (0, -500),
            (500, 0),
        ]
        assert_ledger_consistent(tenant)

    def test_retries_charge_only_the_amount_due(self, api, tenant, clock):
        from ledgerline.payments import service as payments
        from ledgerline.payments.dunning import retry_due_payments

        customer = factories.customer(tenant)
        sub = factories.subscribe(customer, factories.price(tenant, unit_amount=1000))
        payments.attach_payment_method(customer, "tok_failOnce")
        _db.session.commit()
        grant_credit(api, customer.public_id, -400)
        clock.set(JUL_1)
        run_billing_cycle()
        renewal = latest_invoice(sub)
        assert renewal.status == "open"
        clock.set(datetime(2020, 7, 4, 12))
        retry_due_payments()
        assert renewal.status == "paid"
        assert [a.amount for a in renewal.payment_attempts] == [600, 600]
        assert_ledger_consistent(tenant)

    def test_void_restores_applied_credit(self, api, tenant):
        customer = factories.customer(tenant, token=None)
        _db.session.commit()
        grant_credit(api, customer.public_id, -300)
        customer = Customer.query.get(customer.id)
        sub = factories.subscribe(
            customer, factories.price(tenant, unit_amount=1000), collection_method="send_invoice"
        )
        invoice = latest_invoice(sub)
        assert (invoice.status, invoice.amount_due, customer.balance) == ("open", 700, 0)
        invoicing.void_invoice(invoice)
        assert customer.balance == -300
        assert_ledger_consistent(tenant)


class TestApi:
    def test_adjustments(self, api, tenant, clock):
        customer = api.post("/v1/customers", json={}).get_json()
        assert customer["balance"] == 0
        first = grant_credit(api, customer["id"], -500)
        assert first["id"].startswith("cbtxn_")
        assert first["object"] == "customer_balance_transaction"
        assert (first["type"], first["amount"], first["ending_balance"]) == ("adjustment", -500, -500)
        assert (first["currency"], first["invoice"], first["customer"]) == ("eur", None, customer["id"])
        assert first["description"] == "Goodwill"
        clock.advance(seconds=1)
        second = grant_credit(api, customer["id"], -250)
        assert second["ending_balance"] == -750

        fetched = api.get("/v1/customers/%s" % customer["id"]).get_json()
        assert (fetched["balance"], fetched["currency"]) == (-750, "eur")
        listed = api.get("/v1/customers/%s/balance_transactions" % customer["id"]).get_json()
        assert listed["object"] == "list"
        assert [t["id"] for t in listed["data"]] == [second["id"], first["id"]]

        assert balances(tenant)[ADJUSTMENTS] == 750
        assert balances(tenant)[CREDIT] == -750
        assert_ledger_consistent(tenant)

    def test_adjustment_validation(self, api):
        customer = api.post("/v1/customers", json={}).get_json()
        url = "/v1/customers/%s/balance_transactions" % customer["id"]
        for amount in (0, 100):
            response = api.post(url, json={"amount": amount, "currency": "eur"})
            assert response.status_code == 400
            assert response.get_json()["error"]["param"] == "amount"
        grant_credit(api, customer["id"], -100)
        response = api.post(url, json={"amount": -100, "currency": "usd"})
        assert response.status_code == 400
        assert response.get_json()["error"]["param"] == "currency"

    def test_other_tenants_cannot_touch_the_balance(self, api, other_api):
        customer = api.post("/v1/customers", json={}).get_json()
        response = other_api.post(
            "/v1/customers/%s/balance_transactions" % customer["id"],
            json={"amount": -100, "currency": "eur"},
        )
        assert response.status_code == 404

    def test_invoice_exposes_balances(self, api, tenant, clock):
        customer = factories.customer(tenant)
        factories.invoice_item(customer, 1000)
        draft = invoicing.create_manual_invoice(customer)
        _db.session.commit()
        body = api.get("/v1/invoices/%s" % draft.public_id).get_json()
        assert (body["starting_balance"], body["ending_balance"]) == (None, None)
        grant_credit(api, customer.public_id, -400)
        clock.advance(seconds=1)
        body = api.post("/v1/invoices/%s/finalize" % draft.public_id).get_json()
        assert (body["starting_balance"], body["ending_balance"]) == (-400, 0)
        assert body["amount_due"] == 600
        transactions = api.get(
            "/v1/customers/%s/balance_transactions" % customer.public_id
        ).get_json()["data"]
        assert [(t["type"], t["amount"], t["invoice"]) for t in transactions] == [
            ("applied_to_invoice", 400, draft.public_id),
            ("adjustment", -400, None),
        ]


class TestMigration:
    def test_schema_and_existing_customers(self):
        with migration_app() as (app, config):
            upgrade(config, V141_HEAD)
            now = datetime(2020, 10, 1, 12)
            with _db.engine.begin() as connection:
                connection.execute(
                    text(
                        "INSERT INTO tenants (id, public_id, name, home_country, default_currency, "
                        "dunning_retry_days, dunning_final_action, created_at, updated_at) "
                        "VALUES (1, 'acct_1', 'T', 'DE', 'eur', '3,5,7', 'cancel', :now, :now)"
                    ),
                    now=now,
                )
                connection.execute(
                    text(
                        "INSERT INTO customers (id, public_id, tenant_id, invoice_prefix, "
                        "next_invoice_sequence, tax_exempt, created_at, updated_at) "
                        "VALUES (1, 'cus_1', 1, 'ABCDEFGH', 1, 0, :now, :now)"
                    ),
                    now=now,
                )
            upgrade(config, "head")
            inspector = inspect(_db.engine)
            assert "customer_balance_transactions" in inspector.get_table_names()
            invoice_columns = {c["name"] for c in inspector.get_columns("invoices")}
            assert {"starting_balance", "ending_balance"} <= invoice_columns
            with _db.engine.begin() as connection:
                balance = connection.execute(text("SELECT balance FROM customers")).scalar()
            assert balance == 0
            assert schema_diff() == []
            downgrade(config, V141_HEAD)
            assert "customer_balance_transactions" not in inspect(_db.engine).get_table_names()
            upgrade(config, "head")
