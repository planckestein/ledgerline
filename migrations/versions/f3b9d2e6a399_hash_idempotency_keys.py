"""look up idempotency keys by SHA-256 hash

Revision ID: f3b9d2e6a399
Revises: e8a1c4d7b288
Create Date: 2020-11-16 17:25:41.000000

"""
import hashlib

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "f3b9d2e6a399"
down_revision = "e8a1c4d7b288"
branch_labels = None
depends_on = None

idempotency_keys = sa.table(
    "idempotency_keys",
    sa.column("id", sa.Integer),
    sa.column("key", sa.String),
    sa.column("key_hash", sa.String),
)


def upgrade():
    with op.batch_alter_table("idempotency_keys", schema=None) as batch_op:
        batch_op.add_column(sa.Column("key_hash", sa.String(length=64), nullable=True))

    connection = op.get_bind()
    rows = connection.execute(sa.select([idempotency_keys.c.id, idempotency_keys.c.key]))
    for row_id, key in rows.fetchall():
        connection.execute(
            idempotency_keys.update()
            .where(idempotency_keys.c.id == row_id)
            .values(key_hash=hashlib.sha256(key.encode("utf-8")).hexdigest())
        )

    with op.batch_alter_table("idempotency_keys", schema=None) as batch_op:
        batch_op.alter_column("key_hash", existing_type=sa.String(length=64), nullable=False)
        batch_op.drop_constraint("uq_idempotency_keys_tenant_id_key", type_="unique")
        batch_op.create_index(batch_op.f("ix_idempotency_keys_key_hash"), ["key_hash"], unique=True)


def downgrade():
    with op.batch_alter_table("idempotency_keys", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_idempotency_keys_key_hash"))
        batch_op.create_unique_constraint("uq_idempotency_keys_tenant_id_key", ["tenant_id", "key"])
        batch_op.drop_column("key_hash")
