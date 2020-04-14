"""coupons and discounts

Revision ID: 4a7d9e1c2b33
Revises: 1c8e2f3a9b10
Create Date: 2020-04-13 17:41:09.000000

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "4a7d9e1c2b33"
down_revision = "1c8e2f3a9b10"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "coupons",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=True),
        sa.Column("percent_off", sa.Numeric(precision=6, scale=3), nullable=True),
        sa.Column("amount_off", sa.Integer(), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("duration", sa.String(length=20), nullable=False),
        sa.Column("duration_in_months", sa.Integer(), nullable=True),
        sa.Column("max_redemptions", sa.Integer(), nullable=True),
        sa.Column("times_redeemed", sa.Integer(), nullable=False),
        sa.Column("valid", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("public_id", sa.String(length=40), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_coupons_tenant_id_tenants")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_coupons")),
        sa.UniqueConstraint("public_id", name=op.f("uq_coupons_public_id")),
    )
    op.create_index(op.f("ix_coupons_tenant_id"), "coupons", ["tenant_id"], unique=False)

    op.create_table(
        "discounts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("coupon_id", sa.Integer(), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("subscription_id", sa.Integer(), nullable=True),
        sa.Column("start", sa.DateTime(), nullable=False),
        sa.Column("end", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("public_id", sa.String(length=40), nullable=False),
        sa.ForeignKeyConstraint(
            ["coupon_id"], ["coupons.id"], name=op.f("fk_discounts_coupon_id_coupons")
        ),
        sa.ForeignKeyConstraint(
            ["customer_id"], ["customers.id"], name=op.f("fk_discounts_customer_id_customers")
        ),
        sa.ForeignKeyConstraint(
            ["subscription_id"],
            ["subscriptions.id"],
            name=op.f("fk_discounts_subscription_id_subscriptions"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_discounts_tenant_id_tenants")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_discounts")),
        sa.UniqueConstraint("public_id", name=op.f("uq_discounts_public_id")),
    )
    op.create_index(op.f("ix_discounts_customer_id"), "discounts", ["customer_id"], unique=False)
    op.create_index(
        op.f("ix_discounts_subscription_id"), "discounts", ["subscription_id"], unique=False
    )
    op.create_index(op.f("ix_discounts_tenant_id"), "discounts", ["tenant_id"], unique=False)

    with op.batch_alter_table("invoices", schema=None) as batch_op:
        batch_op.add_column(sa.Column("coupon_id", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column("discount_total", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.create_foreign_key(
            batch_op.f("fk_invoices_coupon_id_coupons"), "coupons", ["coupon_id"], ["id"]
        )

    with op.batch_alter_table("invoice_lines", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("discount_amount", sa.Integer(), nullable=False, server_default="0")
        )


def downgrade():
    with op.batch_alter_table("invoice_lines", schema=None) as batch_op:
        batch_op.drop_column("discount_amount")

    with op.batch_alter_table("invoices", schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f("fk_invoices_coupon_id_coupons"), type_="foreignkey")
        batch_op.drop_column("discount_total")
        batch_op.drop_column("coupon_id")

    op.drop_index(op.f("ix_discounts_tenant_id"), table_name="discounts")
    op.drop_index(op.f("ix_discounts_subscription_id"), table_name="discounts")
    op.drop_index(op.f("ix_discounts_customer_id"), table_name="discounts")
    op.drop_table("discounts")
    op.drop_index(op.f("ix_coupons_tenant_id"), table_name="coupons")
    op.drop_table("coupons")
