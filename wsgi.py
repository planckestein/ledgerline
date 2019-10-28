"""WSGI entry point: ``gunicorn wsgi:app``."""
from ledgerline.app import create_app

app = create_app()
