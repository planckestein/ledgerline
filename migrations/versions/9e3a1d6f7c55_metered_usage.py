"""metered prices and usage records

Revision ID: 9e3a1d6f7c55
Revises: 7b2f5c8d1e44
Create Date: 2020-07-06 15:03:12.000000

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "9e3a1d6f7c55"
down_revision = "7b2f5c8d1e44"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("prices", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("usage_type", sa.String(length=10), nullable=False, server_default="licensed")
        )
        batch_op.add_column(sa.Column("aggregate_usage", sa.String(length=30), nullable=True))

    op.create_table(
        "usage_records",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("subscription_item_id", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("public_id", sa.String(length=40), nullable=False),
        sa.ForeignKeyConstraint(
            ["subscription_item_id"],
            ["subscription_items.id"],
            name=op.f("fk_usage_records_subscription_item_id_subscription_items"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_usage_records")),
        sa.UniqueConstraint("public_id", name=op.f("uq_usage_records_public_id")),
    )
    op.create_index(
        op.f("ix_usage_records_subscription_item_id"),
        "usage_records",
        ["subscription_item_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_usage_records_timestamp"), "usage_records", ["timestamp"], unique=False
    )


def downgrade():
    op.drop_index(op.f("ix_usage_records_timestamp"), table_name="usage_records")
    op.drop_index(op.f("ix_usage_records_subscription_item_id"), table_name="usage_records")
    op.drop_table("usage_records")

    with op.batch_alter_table("prices", schema=None) as batch_op:
        batch_op.drop_column("aggregate_usage")
        batch_op.drop_column("usage_type")
