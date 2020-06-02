"""Tax resolution and calculation.

Rate selection (most specific wins, ties broken by lowest id):

1. tax-exempt customers pay no tax;
2. EU B2B reverse charge: customer and tenant are in different EU member
   states and the customer has a VAT id -> no tax;
3. a rate for the customer's country *and* state;
4. a rate for the customer's country;
5. a global rate (country NULL).

Tax is computed per invoice line on the line's net amount (amount minus
discount) and rounded half away from zero to the currency's minor unit.
"""
from decimal import ROUND_HALF_UP, Decimal
from fractions import Fraction

from ledgerline.currency import exponent
from ledgerline.geo import is_eu
from ledgerline.models import TaxRate
from ledgerline.money import round_half_up

EXEMPT = "customer_exempt"
REVERSE_CHARGE = "reverse_charge"
NO_RATE = "no_rate"
STANDARD = "standard"


def resolve_tax_rate(customer):
    """Return ``(tax_rate_or_None, reason)`` for invoices of ``customer``."""
    if customer.tax_exempt:
        return None, EXEMPT

    tenant = customer.tenant
    country = customer.billing_country
    state = customer.billing_state
    if (
        country
        and country != tenant.home_country
        and is_eu(country)
        and is_eu(tenant.home_country)
        and customer.vat_id
    ):
        return None, REVERSE_CHARGE

    rates = (
        TaxRate.query.filter_by(tenant_id=customer.tenant_id, active=True)
        .order_by(TaxRate.id)
        .all()
    )
    best, best_score = None, -1
    for rate in rates:
        if rate.country is None:
            score = 0
        elif country and rate.country == country:
            if rate.state is None:
                score = 1
            elif state and rate.state.upper() == state.upper():
                score = 2
            else:
                continue
        else:
            continue
        if score > best_score:
            best, best_score = rate, score
    return best, (STANDARD if best is not None else NO_RATE)


def compute_tax(net_amount, rate, currency):
    """Tax in minor units for a line whose net amount is ``net_amount``."""
    if rate is None or net_amount == 0:
        return 0
    if rate.inclusive:
        # The net amount already contains the tax: tax = net - net / (1 + p).
        factor = 1 + Fraction(Decimal(rate.percentage)) / 100
        return net_amount - round_half_up(Fraction(net_amount) / factor)

    major = Decimal(net_amount) / (10 ** exponent(currency))
    tax_major = (major * Decimal(rate.percentage) / 100).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    return int(tax_major * 100)


def apply_taxes(invoice, lines):
    """Resolve the tax rate for ``invoice`` and set tax fields on every line."""
    rate, reason = resolve_tax_rate(invoice.customer)
    for line in lines:
        line.tax_rate = rate
        line.tax_inclusive = bool(rate.inclusive) if rate is not None else False
        line.tax_amount = compute_tax(line.amount - line.discount_amount, rate, invoice.currency)
    return rate, reason
