"""Helpers for running Alembic against a throw-away SQLite database."""
import contextlib
import os
import shutil
import tempfile

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from flask_migrate import Migrate

from ledgerline.app import MIGRATIONS_DIR, create_app
from ledgerline.extensions import db


@contextlib.contextmanager
def migration_app():
    """Yield ``(app, alembic_config)`` bound to a fresh file-backed SQLite database."""
    directory = tempfile.mkdtemp(prefix="ledgerline-migrations-")
    path = os.path.join(directory, "migrations.db")
    app = create_app("testing", SQLALCHEMY_DATABASE_URI="sqlite:///" + path.replace("\\", "/"))
    try:
        with app.app_context():
            migrate = app.extensions["migrate"].migrate
            assert isinstance(migrate, Migrate)
            config = migrate.get_config(MIGRATIONS_DIR)
            yield app, config
            db.session.remove()
            db.engine.dispose()
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def upgrade(config, revision="head"):
    command.upgrade(config, revision)


def downgrade(config, revision):
    command.downgrade(config, revision)


def schema_diff():
    """Differences between the migrated database and the SQLAlchemy models."""
    with db.engine.connect() as connection:
        context = MigrationContext.configure(connection, opts={"render_as_batch": True})
        return compare_metadata(context, db.metadata)
