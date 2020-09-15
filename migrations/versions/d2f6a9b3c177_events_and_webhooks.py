"""events outbox and webhook deliveries

Revision ID: d2f6a9b3c177
Revises: b5c8e2a4f066
Create Date: 2020-09-14 16:10:28.000000

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "d2f6a9b3c177"
down_revision = "b5c8e2a4f066"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(length=60), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("public_id", sa.String(length=40), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_events_tenant_id_tenants")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_events")),
        sa.UniqueConstraint("public_id", name=op.f("uq_events_public_id")),
    )
    op.create_index(op.f("ix_events_tenant_id"), "events", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_events_type"), "events", ["type"], unique=False)

    op.create_table(
        "webhook_endpoints",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("url", sa.String(length=500), nullable=False),
        sa.Column("secret", sa.String(length=64), nullable=False),
        sa.Column("enabled_events", sa.Text(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("public_id", sa.String(length=40), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_webhook_endpoints_tenant_id_tenants")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_webhook_endpoints")),
        sa.UniqueConstraint("public_id", name=op.f("uq_webhook_endpoints_public_id")),
    )
    op.create_index(
        op.f("ix_webhook_endpoints_tenant_id"), "webhook_endpoints", ["tenant_id"], unique=False
    )

    op.create_table(
        "webhook_deliveries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("endpoint_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(), nullable=True),
        sa.Column("last_attempt_at", sa.DateTime(), nullable=True),
        sa.Column("response_status", sa.Integer(), nullable=True),
        sa.Column("last_error", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["endpoint_id"],
            ["webhook_endpoints.id"],
            name=op.f("fk_webhook_deliveries_endpoint_id_webhook_endpoints"),
        ),
        sa.ForeignKeyConstraint(
            ["event_id"], ["events.id"], name=op.f("fk_webhook_deliveries_event_id_events")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_webhook_deliveries")),
    )
    op.create_index(
        op.f("ix_webhook_deliveries_endpoint_id"),
        "webhook_deliveries",
        ["endpoint_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_webhook_deliveries_event_id"), "webhook_deliveries", ["event_id"], unique=False
    )
    op.create_index(
        op.f("ix_webhook_deliveries_next_attempt_at"),
        "webhook_deliveries",
        ["next_attempt_at"],
        unique=False,
    )


def downgrade():
    op.drop_index(op.f("ix_webhook_deliveries_next_attempt_at"), table_name="webhook_deliveries")
    op.drop_index(op.f("ix_webhook_deliveries_event_id"), table_name="webhook_deliveries")
    op.drop_index(op.f("ix_webhook_deliveries_endpoint_id"), table_name="webhook_deliveries")
    op.drop_table("webhook_deliveries")
    op.drop_index(op.f("ix_webhook_endpoints_tenant_id"), table_name="webhook_endpoints")
    op.drop_table("webhook_endpoints")
    op.drop_index(op.f("ix_events_type"), table_name="events")
    op.drop_index(op.f("ix_events_tenant_id"), table_name="events")
    op.drop_table("events")
