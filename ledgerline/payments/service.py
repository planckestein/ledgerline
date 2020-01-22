"""Collecting invoice payments and managing payment methods."""
from ledgerline import clock
from ledgerline.billing import invoicing
from ledgerline.errors import InvalidRequestError, InvalidStateTransition
from ledgerline.extensions import db
from ledgerline.models import PaymentAttempt, PaymentMethod
from ledgerline.payments import dunning
from ledgerline.payments.gateway import ChargeResult, get_gateway


def attach_payment_method(customer, token, set_default=True):
    try:
        brand, last4 = get_gateway().describe_token(token)
    except ValueError:
        raise InvalidRequestError("Invalid payment token", param="token", code="invalid_token")
    method = PaymentMethod(
        tenant_id=customer.tenant_id,
        customer=customer,
        token=token,
        card_brand=brand,
        card_last4=last4,
        is_default=False,
    )
    is_first = customer.default_payment_method is None
    db.session.add(method)
    if set_default or is_first:
        for other in customer.payment_methods:
            other.is_default = False
        method.is_default = True
    return method


def collect_invoice(invoice):
    """Attempt to charge the customer's default payment method for ``invoice``.

    Returns the :class:`PaymentAttempt`. A declined charge is *not* an
    exception: it is recorded and handed to dunning.
    """
    if invoice.status not in ("open", "uncollectible"):
        raise InvalidStateTransition(
            "Invoice %s is %s and cannot be charged" % (invoice.public_id, invoice.status)
        )
    if invoice.amount_due <= 0:
        raise InvalidRequestError("Invoice %s has nothing to collect" % invoice.public_id)

    now = clock.utcnow()
    method = invoice.customer.default_payment_method
    invoice.attempt_count += 1
    key = "%s:attempt:%d" % (invoice.public_id, invoice.attempt_count)
    if method is None:
        result = ChargeResult(
            False, None, "no_payment_method", "Customer has no default payment method."
        )
    else:
        result = get_gateway().charge(
            amount=invoice.amount_due,
            currency=invoice.currency,
            token=method.token,
            idempotency_key=key,
            description="Invoice %s" % invoice.number,
        )

    attempt = PaymentAttempt(
        tenant_id=invoice.tenant_id,
        invoice=invoice,
        payment_method=method,
        amount=invoice.amount_due,
        currency=invoice.currency,
        status="succeeded" if result.succeeded else "failed",
        failure_code=result.failure_code,
        failure_message=result.failure_message,
        gateway_reference=result.reference,
        idempotency_key=key,
        created_at=now,
    )
    db.session.add(attempt)

    if result.succeeded:
        invoicing.mark_paid(invoice, amount=attempt.amount, attempt=attempt)
    else:
        dunning.handle_payment_failure(invoice, attempt, now)
    return attempt
