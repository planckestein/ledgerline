"""double-entry ledger

Revision ID: b5c8e2a4f066
Revises: 9e3a1d6f7c55
Create Date: 2020-08-24 14:37:55.000000

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "b5c8e2a4f066"
down_revision = "9e3a1d6f7c55"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "journal_entries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("reference_type", sa.String(length=30), nullable=False),
        sa.Column("reference_id", sa.String(length=40), nullable=False),
        sa.Column("memo", sa.String(length=255), nullable=True),
        sa.Column("posted_at", sa.DateTime(), nullable=False),
        sa.Column("public_id", sa.String(length=40), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_journal_entries_tenant_id_tenants")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_journal_entries")),
        sa.UniqueConstraint("public_id", name=op.f("uq_journal_entries_public_id")),
    )
    op.create_index(
        op.f("ix_journal_entries_reference_id"), "journal_entries", ["reference_id"], unique=False
    )
    op.create_index(
        op.f("ix_journal_entries_tenant_id"), "journal_entries", ["tenant_id"], unique=False
    )

    op.create_table(
        "journal_lines",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("entry_id", sa.Integer(), nullable=False),
        sa.Column("account", sa.String(length=40), nullable=False),
        sa.Column("debit", sa.Integer(), nullable=False),
        sa.Column("credit", sa.Integer(), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["customer_id"], ["customers.id"], name=op.f("fk_journal_lines_customer_id_customers")
        ),
        sa.ForeignKeyConstraint(
            ["entry_id"],
            ["journal_entries.id"],
            name=op.f("fk_journal_lines_entry_id_journal_entries"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_journal_lines")),
    )
    op.create_index(op.f("ix_journal_lines_account"), "journal_lines", ["account"], unique=False)
    op.create_index(
        op.f("ix_journal_lines_customer_id"), "journal_lines", ["customer_id"], unique=False
    )
    op.create_index(op.f("ix_journal_lines_entry_id"), "journal_lines", ["entry_id"], unique=False)


def downgrade():
    op.drop_index(op.f("ix_journal_lines_entry_id"), table_name="journal_lines")
    op.drop_index(op.f("ix_journal_lines_customer_id"), table_name="journal_lines")
    op.drop_index(op.f("ix_journal_lines_account"), table_name="journal_lines")
    op.drop_table("journal_lines")
    op.drop_index(op.f("ix_journal_entries_tenant_id"), table_name="journal_entries")
    op.drop_index(op.f("ix_journal_entries_reference_id"), table_name="journal_entries")
    op.drop_table("journal_entries")
