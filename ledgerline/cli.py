"""``flask`` CLI commands for operators."""
import json

import click
from flask.cli import AppGroup

from ledgerline.currency import normalize_currency
from ledgerline.extensions import db
from ledgerline.geo import normalize_country
from ledgerline.models import ApiKey, Tenant

tenants_cli = AppGroup("tenants", help="Manage tenants and API keys.")
billing_cli = AppGroup("billing", help="Run billing jobs by hand.")
ledger_cli = AppGroup("ledger", help="Inspect the double-entry ledger.")


@tenants_cli.command("create")
@click.option("--name", required=True)
@click.option("--country", required=True, help="ISO country code of the merchant.")
@click.option("--currency", required=True, help="Default currency, e.g. eur.")
def create_tenant(name, country, currency):
    """Create a tenant and print its first API key."""
    tenant = Tenant(
        name=name,
        home_country=normalize_country(country),
        default_currency=normalize_currency(currency),
    )
    db.session.add(tenant)
    _, secret = ApiKey.issue(tenant)
    db.session.commit()
    click.echo("tenant: %s" % tenant.public_id)
    click.echo("api key: %s  (shown once)" % secret)


@tenants_cli.command("issue-key")
@click.argument("tenant_id")
def issue_key(tenant_id):
    tenant = Tenant.query.filter_by(public_id=tenant_id).first()
    if tenant is None:
        raise click.ClickException("No such tenant %s" % tenant_id)
    _, secret = ApiKey.issue(tenant)
    db.session.commit()
    click.echo(secret)


@billing_cli.command("run")
def billing_run():
    """Renew every subscription whose period has ended."""
    from ledgerline.billing.renewal import run_billing_cycle

    click.echo(json.dumps(run_billing_cycle(), indent=2))


@billing_cli.command("retry-payments")
def billing_retry_payments():
    """Retry every invoice whose next payment attempt is due."""
    from ledgerline.payments.dunning import retry_due_payments

    click.echo(json.dumps(retry_due_payments(), indent=2))


@billing_cli.command("dispatch-webhooks")
def billing_dispatch_webhooks():
    from ledgerline.events.webhooks import dispatch_due

    click.echo(json.dumps(dispatch_due(), indent=2))


@billing_cli.command("purge-idempotency-keys")
def billing_purge_idempotency_keys():
    from ledgerline.api.idempotency import purge_expired

    click.echo("deleted %d keys" % purge_expired())


@ledger_cli.command("trial-balance")
@click.argument("tenant_id")
@click.option("--currency", default=None, help="Defaults to the tenant's default currency.")
def ledger_trial_balance(tenant_id, currency):
    """Print the trial balance of a tenant; exits with status 1 if it does not balance."""
    from ledgerline.ledger.reports import trial_balance

    tenant = Tenant.query.filter_by(public_id=tenant_id).first()
    if tenant is None:
        raise click.ClickException("No such tenant %s" % tenant_id)
    report = trial_balance(tenant.id, normalize_currency(currency or tenant.default_currency))
    for row in report["accounts"]:
        click.echo(
            "%-28s %12d %12d %12d" % (row["account"], row["debits"], row["credits"], row["balance"])
        )
    click.echo("%-28s %12d %12d" % ("total", report["total_debits"], report["total_credits"]))
    if not report["balanced"]:
        raise click.ClickException("Ledger does not balance")


def register_cli(app):
    app.cli.add_command(tenants_cli)
    app.cli.add_command(billing_cli)
    app.cli.add_command(ledger_cli)
