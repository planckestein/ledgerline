"""tax rates, customer tax status and per-line tax

Revision ID: 7b2f5c8d1e44
Revises: 4a7d9e1c2b33
Create Date: 2020-06-01 16:22:47.000000

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "7b2f5c8d1e44"
down_revision = "4a7d9e1c2b33"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "tax_rates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("display_name", sa.String(length=100), nullable=False),
        sa.Column("percentage", sa.Numeric(precision=7, scale=4), nullable=False),
        sa.Column("inclusive", sa.Boolean(), nullable=False),
        sa.Column("country", sa.String(length=2), nullable=True),
        sa.Column("state", sa.String(length=10), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("public_id", sa.String(length=40), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_tax_rates_tenant_id_tenants")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tax_rates")),
        sa.UniqueConstraint("public_id", name=op.f("uq_tax_rates_public_id")),
    )
    op.create_index(op.f("ix_tax_rates_tenant_id"), "tax_rates", ["tenant_id"], unique=False)

    with op.batch_alter_table("customers", schema=None) as batch_op:
        batch_op.add_column(sa.Column("vat_id", sa.String(length=64), nullable=True))
        batch_op.add_column(
            sa.Column("tax_exempt", sa.Boolean(), nullable=False, server_default=sa.false())
        )

    with op.batch_alter_table("invoices", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("tax_total", sa.Integer(), nullable=False, server_default="0")
        )

    with op.batch_alter_table("invoice_lines", schema=None) as batch_op:
        batch_op.add_column(sa.Column("tax_rate_id", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column("tax_amount", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.add_column(
            sa.Column("tax_inclusive", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch_op.create_foreign_key(
            batch_op.f("fk_invoice_lines_tax_rate_id_tax_rates"),
            "tax_rates",
            ["tax_rate_id"],
            ["id"],
        )


def downgrade():
    with op.batch_alter_table("invoice_lines", schema=None) as batch_op:
        batch_op.drop_constraint(
            batch_op.f("fk_invoice_lines_tax_rate_id_tax_rates"), type_="foreignkey"
        )
        batch_op.drop_column("tax_inclusive")
        batch_op.drop_column("tax_amount")
        batch_op.drop_column("tax_rate_id")

    with op.batch_alter_table("invoices", schema=None) as batch_op:
        batch_op.drop_column("tax_total")

    with op.batch_alter_table("customers", schema=None) as batch_op:
        batch_op.drop_column("tax_exempt")
        batch_op.drop_column("vat_id")

    op.drop_index(op.f("ix_tax_rates_tenant_id"), table_name="tax_rates")
    op.drop_table("tax_rates")
