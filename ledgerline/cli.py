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


def register_cli(app):
    app.cli.add_command(tenants_cli)
    app.cli.add_command(billing_cli)
