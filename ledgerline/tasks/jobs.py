"""Periodic jobs. Each job is safe to run concurrently with itself."""
from ledgerline.billing.renewal import run_billing_cycle
from ledgerline.payments.dunning import retry_due_payments
from ledgerline.tasks import celery


@celery.task(name="ledgerline.run_billing_cycle")
def run_billing_cycle_task():
    return run_billing_cycle()


@celery.task(name="ledgerline.retry_due_payments")
def retry_due_payments_task():
    return retry_due_payments()
