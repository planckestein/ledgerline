from datetime import datetime, timedelta

from ledgerline.billing.renewal import run_billing_cycle
from ledgerline.models import Event, Invoice, PaymentAttempt
from ledgerline.payments import service as payments
from ledgerline.payments.dunning import retry_due_payments
from tests.support import factories

JUL_1 = datetime(2020, 7, 1, 12)


def renewal_that_fails(tenant, clock, token="tok_chargeDeclined"):
    customer = factories.customer(tenant)
    sub = factories.subscribe(customer, factories.price(tenant, unit_amount=1000))
    payments.attach_payment_method(customer, token)
    clock.set(JUL_1)
    run_billing_cycle()
    invoice = Invoice.query.filter_by(subscription_id=sub.id).order_by(Invoice.id.desc()).first()
    return customer, sub, invoice


def test_retries_follow_the_tenant_schedule_then_cancel(tenant, clock):
    customer, sub, invoice = renewal_that_fails(tenant, clock)
    assert invoice.attempt_count == 1
    assert sub.status == "past_due"

    expected_waits = [3, 5, 7]
    for attempt, wait in enumerate(expected_waits, start=2):
        assert invoice.next_payment_attempt == clock.now() + timedelta(days=wait)
        clock.advance(days=wait)
        summary = retry_due_payments()
        assert summary["attempted"] == 1
        assert invoice.attempt_count == attempt

    assert invoice.next_payment_attempt is None
    assert invoice.status == "uncollectible"
    assert sub.status == "canceled"
    assert sub.ended_at == clock.now()


def test_retries_are_not_attempted_early(tenant, clock):
    _, _, invoice = renewal_that_fails(tenant, clock)
    clock.advance(days=2, hours=23)
    assert retry_due_payments()["attempted"] == 0
    assert invoice.attempt_count == 1


def test_mark_unpaid_final_action(tenant, clock):
    tenant.dunning_retry_days = "1"
    tenant.dunning_final_action = "mark_unpaid"
    _, sub, invoice = renewal_that_fails(tenant, clock)
    clock.advance(days=1)
    retry_due_payments()
    assert sub.status == "unpaid"
    assert invoice.status == "open"
    clock.set(datetime(2020, 9, 1))
    assert run_billing_cycle()["subscriptions"] == 0


def test_successful_retry_reactivates_subscription(tenant, clock):
    _, sub, invoice = renewal_that_fails(tenant, clock, token="tok_failOnce")
    assert sub.status == "past_due"
    clock.advance(days=3)
    assert retry_due_payments()["succeeded"] == 1
    assert invoice.status == "paid"
    assert invoice.next_payment_attempt is None
    assert sub.status == "active"


def test_each_attempt_uses_a_distinct_gateway_idempotency_key(tenant, clock, gateway):
    _, _, invoice = renewal_that_fails(tenant, clock)
    clock.advance(days=3)
    retry_due_payments()
    keys = [a.idempotency_key for a in PaymentAttempt.query.filter_by(invoice_id=invoice.id)]
    assert keys == ["%s:attempt:1" % invoice.public_id, "%s:attempt:2" % invoice.public_id]
    assert len({charge["idempotency_key"] for charge in gateway.charges}) == len(gateway.charges)


def test_failure_publishes_event(tenant, clock):
    _, _, invoice = renewal_that_fails(tenant, clock)
    types = [e.type for e in Event.query.order_by(Event.id)]
    assert "invoice.payment_failed" in types
    assert types.count("customer.subscription.updated") >= 1


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
