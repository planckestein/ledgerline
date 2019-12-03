from __future__ import with_statement

import logging
from logging.config import fileConfig

from alembic import context
from flask import current_app
from sqlalchemy import engine_from_config, pool

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
fileConfig(config.config_file_name, disable_existing_loggers=False)
logger = logging.getLogger("alembic.env")

config.set_main_option(
    "sqlalchemy.url",
    str(current_app.extensions["migrate"].db.engine.url).replace("%", "%%"),
)
target_metadata = current_app.extensions["migrate"].db.metadata


def run_migrations_offline():
    """Run migrations in 'offline' mode (emit SQL to stdout)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        **current_app.extensions["migrate"].configure_args,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    """Run migrations in 'online' mode."""

    # this callback is used to prevent an auto-migration from being generated
    # when there are no changes to the schema
    # reference: http://alembic.zzzcomputing.com/en/latest/cookbook.html
    def process_revision_directives(context, revision, directives):
        if getattr(config.cmd_opts, "autogenerate", False):
            script = directives[0]
            if script.upgrade_ops.is_empty():
                directives[:] = []
                logger.info("No changes in schema detected.")

    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        if connection.dialect.name == "sqlite":
            # Batch migrations recreate tables; SQLite must not enforce foreign
            # keys while a referenced table is being copied and renamed.
            connection.execute("PRAGMA foreign_keys=OFF")

        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            process_revision_directives=process_revision_directives,
            **current_app.extensions["migrate"].configure_args,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
