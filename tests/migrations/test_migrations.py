"""Migrations must apply cleanly, round-trip, and match the models exactly."""
import os

from alembic.script import ScriptDirectory
from sqlalchemy import inspect

from ledgerline.app import MIGRATIONS_DIR
from ledgerline.extensions import db
from tests.support.migrations import downgrade, migration_app, schema_diff, upgrade


def test_single_head():
    with migration_app() as (app, config):
        heads = ScriptDirectory.from_config(config).get_heads()
    assert len(heads) == 1, "Multiple migration heads: %s" % heads


def test_upgrade_to_head_matches_models():
    with migration_app() as (app, config):
        upgrade(config, "head")
        diff = schema_diff()
    assert diff == [], "Models and migrations disagree:\n%s" % "\n".join(map(str, diff))


def test_full_downgrade_and_upgrade_round_trip():
    with migration_app() as (app, config):
        upgrade(config, "head")
        downgrade(config, "base")
        tables = set(inspect(db.engine).get_table_names()) - {"alembic_version"}
        assert tables == set()
        upgrade(config, "head")
        assert schema_diff() == []


def test_every_revision_has_a_downgrade():
    versions = os.path.join(MIGRATIONS_DIR, "versions")
    for name in sorted(os.listdir(versions)):
        if not name.endswith(".py"):
            continue
        with open(os.path.join(versions, name), encoding="utf-8") as handle:
            source = handle.read()
        downgrade_body = source.split("def downgrade():", 1)[1]
        assert downgrade_body.strip() not in ("", "pass"), "%s has no downgrade" % name
