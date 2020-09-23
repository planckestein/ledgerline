"""Celery integration.

The worker is started with ``celery -A celery_worker.celery worker -B``; every
task runs inside a Flask application context.
"""
from celery import Celery

celery = Celery("ledgerline", include=["ledgerline.tasks.jobs"])

BEAT_SCHEDULE = {
    "billing-cycle": {"task": "ledgerline.run_billing_cycle", "schedule": 300.0},
    "payment-retries": {"task": "ledgerline.retry_due_payments", "schedule": 900.0},
    "webhook-dispatch": {"task": "ledgerline.dispatch_webhooks", "schedule": 15.0},
}


def init_celery(app):
    celery.conf.update(
        broker_url=app.config["CELERY_BROKER_URL"],
        result_backend=app.config["CELERY_RESULT_BACKEND"],
        task_always_eager=app.config["CELERY_TASK_ALWAYS_EAGER"],
        task_eager_propagates=True,
        task_serializer="json",
        accept_content=["json"],
        timezone="UTC",
        beat_schedule=BEAT_SCHEDULE,
    )

    class ContextTask(celery.Task):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)

    celery.Task = ContextTask
    app.extensions["celery"] = celery
    return celery
