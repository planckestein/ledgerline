from datetime import datetime

from ledgerline.models import ApiKey, Invoice, Tenant
from ledgerline.tasks import BEAT_SCHEDULE, jobs
from tests.support import factories


def test_celery_tasks_run_eagerly(db, tenant, clock):
    sub_id = factories.subscribe(factories.customer(tenant), factories.price(tenant)).id
    db.session.commit()
    clock.set(datetime(2020, 7, 1, 12))
    result = jobs.run_billing_cycle_task.delay().get()
    assert result["invoices"] == 1
    assert Invoice.query.filter_by(subscription_id=sub_id).count() == 2
    assert jobs.retry_due_payments_task.delay().get()["attempted"] == 0


def test_beat_schedule_references_registered_tasks():
    from ledgerline.tasks import celery

    for entry in BEAT_SCHEDULE.values():
        assert entry["task"] in celery.tasks


def test_cli_creates_tenant_with_api_key(app, db):
    runner = app.test_cli_runner()
    result = runner.invoke(
        args=["tenants", "create", "--name", "Initech", "--country", "us", "--currency", "USD"]
    )
    assert result.exit_code == 0, result.output
    tenant = Tenant.query.filter_by(name="Initech").one()
    assert (tenant.home_country, tenant.default_currency) == ("US", "usd")
    secret = result.output.split("api key: ")[1].split()[0]
    assert ApiKey.query.filter_by(key_hash=ApiKey.hash_secret(secret)).count() == 1


def test_cli_billing_run(app, db, tenant, clock):
    factories.subscribe(factories.customer(tenant), factories.price(tenant))
    db.session.commit()
    clock.set(datetime(2020, 7, 1, 12))
    result = app.test_cli_runner().invoke(args=["billing", "run"])
    assert result.exit_code == 0, result.output
    assert '"invoices": 1' in result.output
