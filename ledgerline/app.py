"""Application factory."""
import logging
import os
import sqlite3

from flask import Flask, jsonify
from sqlalchemy import event
from sqlalchemy.engine import Engine

from ledgerline import __version__
from ledgerline.config import get_config
from ledgerline.extensions import db, migrate

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIGRATIONS_DIR = os.path.join(ROOT, "migrations")


@event.listens_for(Engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, connection_record):
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def create_app(config_name=None, **overrides):
    app = Flask(__name__)
    app.config.from_object(get_config(config_name))
    app.config.update(overrides)

    db.init_app(app)
    migrate.init_app(app, db, directory=MIGRATIONS_DIR, render_as_batch=True)

    from ledgerline import models  # noqa: F401  (register mappers)

    @app.route("/health")
    def health():
        return jsonify({"status": "ok", "version": __version__})

    if not app.debug and not app.testing:
        logging.basicConfig(
            level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
        )
    return app
