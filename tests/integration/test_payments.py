from datetime import datetime

from ledgerline.payments import service as payments
from tests.support import factories

JUL_1 = datetime(2020, 7, 1, 12)


def test_missing_payment_method_is_a_failed_attempt(tenant):
    customer = factories.customer(tenant, token=None)
    factories.invoice_item(customer, 1000)
    from ledgerline.billing import invoicing

    invoice = invoicing.create_manual_invoice(customer)
    invoicing.finalize_invoice(invoice)
    attempt = invoicing.pay_invoice(invoice)
    assert attempt.status == "failed"
    assert attempt.failure_code == "no_payment_method"
    assert invoice.status == "open"


def test_attaching_a_card_makes_it_default(tenant):
    customer = factories.customer(tenant)
    first = customer.default_payment_method
    second = payments.attach_payment_method(customer, "tok_mastercard")
    assert customer.default_payment_method is second
    assert first.is_default is False
    assert second.card_last4 == "4444"
    third = payments.attach_payment_method(customer, "tok_visa", set_default=False)
    assert customer.default_payment_method is second
    assert third.is_default is False
