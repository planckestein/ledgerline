"""Celery entry point: ``celery -A celery_worker.celery worker -B -l info``."""
from ledgerline.app import create_app
from ledgerline.tasks import celery  # noqa: F401

app = create_app()
