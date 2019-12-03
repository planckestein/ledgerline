"""initial schema: tenants, customers, catalog, subscriptions, invoices, payments

Revision ID: 1c8e2f3a9b10
Revises:
Create Date: 2019-12-02 16:52:31.000000

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "1c8e2f3a9b10"
down_revision = None
branch_labels = None
depends_on = None


def _timestamps():
    return [
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    ]


def upgrade():
    op.create_table(
        "tenants",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("home_country", sa.String(length=2), nullable=False),
        sa.Column("default_currency", sa.String(length=3), nullable=False),
        sa.Column("dunning_retry_days", sa.String(length=50), nullable=False),
        sa.Column("dunning_final_action", sa.String(length=20), nullable=False),
        *_timestamps(),
        sa.Column("public_id", sa.String(length=40), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tenants")),
        sa.UniqueConstraint("public_id", name=op.f("uq_tenants_public_id")),
    )

    op.create_table(
        "api_keys",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("key_prefix", sa.String(length=16), nullable=False),
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_api_keys_tenant_id_tenants")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_api_keys")),
        sa.UniqueConstraint("key_hash", name=op.f("uq_api_keys_key_hash")),
    )
    op.create_index(op.f("ix_api_keys_tenant_id"), "api_keys", ["tenant_id"], unique=False)

    op.create_table(
        "customers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("billing_address", sa.Text(), nullable=True),
        sa.Column("invoice_prefix", sa.String(length=12), nullable=False),
        sa.Column("next_invoice_sequence", sa.Integer(), nullable=False),
        sa.Column("metadata", sa.Text(), nullable=True),
        *_timestamps(),
        sa.Column("public_id", sa.String(length=40), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_customers_tenant_id_tenants")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_customers")),
        sa.UniqueConstraint("public_id", name=op.f("uq_customers_public_id")),
        sa.UniqueConstraint(
            "tenant_id", "invoice_prefix", name="uq_customers_tenant_id_invoice_prefix"
        ),
    )
    op.create_index(op.f("ix_customers_tenant_id"), "customers", ["tenant_id"], unique=False)

    op.create_table(
        "payment_methods",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(length=20), nullable=False),
        sa.Column("card_brand", sa.String(length=20), nullable=True),
        sa.Column("card_last4", sa.String(length=4), nullable=True),
        sa.Column("token", sa.String(length=64), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("detached_at", sa.DateTime(), nullable=True),
        *_timestamps(),
        sa.Column("public_id", sa.String(length=40), nullable=False),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.id"],
            name=op.f("fk_payment_methods_customer_id_customers"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_payment_methods_tenant_id_tenants")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_payment_methods")),
        sa.UniqueConstraint("public_id", name=op.f("uq_payment_methods_public_id")),
    )
    op.create_index(
        op.f("ix_payment_methods_customer_id"), "payment_methods", ["customer_id"], unique=False
    )
    op.create_index(
        op.f("ix_payment_methods_tenant_id"), "payment_methods", ["tenant_id"], unique=False
    )

    op.create_table(
        "products",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        *_timestamps(),
        sa.Column("public_id", sa.String(length=40), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_products_tenant_id_tenants")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_products")),
        sa.UniqueConstraint("public_id", name=op.f("uq_products_public_id")),
    )
    op.create_index(op.f("ix_products_tenant_id"), "products", ["tenant_id"], unique=False)

    op.create_table(
        "prices",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("nickname", sa.String(length=200), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("unit_amount", sa.Integer(), nullable=False),
        sa.Column("billing_scheme", sa.String(length=20), nullable=False),
        sa.Column("package_size", sa.Integer(), nullable=True),
        sa.Column("interval", sa.String(length=10), nullable=False),
        sa.Column("interval_count", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        *_timestamps(),
        sa.Column("public_id", sa.String(length=40), nullable=False),
        sa.ForeignKeyConstraint(
            ["product_id"], ["products.id"], name=op.f("fk_prices_product_id_products")
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_prices_tenant_id_tenants")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_prices")),
        sa.UniqueConstraint("public_id", name=op.f("uq_prices_public_id")),
    )
    op.create_index(op.f("ix_prices_product_id"), "prices", ["product_id"], unique=False)
    op.create_index(op.f("ix_prices_tenant_id"), "prices", ["tenant_id"], unique=False)

    op.create_table(
        "subscriptions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("collection_method", sa.String(length=30), nullable=False),
        sa.Column("days_until_due", sa.Integer(), nullable=True),
        sa.Column("billing_cycle_anchor", sa.DateTime(), nullable=False),
        sa.Column("current_period_start", sa.DateTime(), nullable=False),
        sa.Column("current_period_end", sa.DateTime(), nullable=False),
        sa.Column("trial_start", sa.DateTime(), nullable=True),
        sa.Column("trial_end", sa.DateTime(), nullable=True),
        sa.Column("cancel_at_period_end", sa.Boolean(), nullable=False),
        sa.Column("canceled_at", sa.DateTime(), nullable=True),
        sa.Column("ended_at", sa.DateTime(), nullable=True),
        *_timestamps(),
        sa.Column("public_id", sa.String(length=40), nullable=False),
        sa.ForeignKeyConstraint(
            ["customer_id"], ["customers.id"], name=op.f("fk_subscriptions_customer_id_customers")
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_subscriptions_tenant_id_tenants")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_subscriptions")),
        sa.UniqueConstraint("public_id", name=op.f("uq_subscriptions_public_id")),
    )
    op.create_index(
        op.f("ix_subscriptions_current_period_end"),
        "subscriptions",
        ["current_period_end"],
        unique=False,
    )
    op.create_index(
        op.f("ix_subscriptions_customer_id"), "subscriptions", ["customer_id"], unique=False
    )
    op.create_index(
        op.f("ix_subscriptions_tenant_id"), "subscriptions", ["tenant_id"], unique=False
    )

    op.create_table(
        "subscription_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("subscription_id", sa.Integer(), nullable=False),
        sa.Column("price_id", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        *_timestamps(),
        sa.Column("public_id", sa.String(length=40), nullable=False),
        sa.ForeignKeyConstraint(
            ["price_id"], ["prices.id"], name=op.f("fk_subscription_items_price_id_prices")
        ),
        sa.ForeignKeyConstraint(
            ["subscription_id"],
            ["subscriptions.id"],
            name=op.f("fk_subscription_items_subscription_id_subscriptions"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_subscription_items_tenant_id_tenants")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_subscription_items")),
        sa.UniqueConstraint("public_id", name=op.f("uq_subscription_items_public_id")),
    )
    op.create_index(
        op.f("ix_subscription_items_price_id"), "subscription_items", ["price_id"], unique=False
    )
    op.create_index(
        op.f("ix_subscription_items_subscription_id"),
        "subscription_items",
        ["subscription_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_subscription_items_tenant_id"), "subscription_items", ["tenant_id"], unique=False
    )

    op.create_table(
        "invoices",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("subscription_id", sa.Integer(), nullable=True),
        sa.Column("number", sa.String(length=40), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("billing_reason", sa.String(length=30), nullable=False),
        sa.Column("collection_method", sa.String(length=30), nullable=False),
        sa.Column("days_until_due", sa.Integer(), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("period_start", sa.DateTime(), nullable=True),
        sa.Column("period_end", sa.DateTime(), nullable=True),
        sa.Column("subtotal", sa.Integer(), nullable=False),
        sa.Column("total", sa.Integer(), nullable=False),
        sa.Column("amount_due", sa.Integer(), nullable=False),
        sa.Column("amount_paid", sa.Integer(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("next_payment_attempt", sa.DateTime(), nullable=True),
        sa.Column("due_date", sa.DateTime(), nullable=True),
        sa.Column("finalized_at", sa.DateTime(), nullable=True),
        sa.Column("paid_at", sa.DateTime(), nullable=True),
        sa.Column("voided_at", sa.DateTime(), nullable=True),
        sa.Column("marked_uncollectible_at", sa.DateTime(), nullable=True),
        *_timestamps(),
        sa.Column("public_id", sa.String(length=40), nullable=False),
        sa.ForeignKeyConstraint(
            ["customer_id"], ["customers.id"], name=op.f("fk_invoices_customer_id_customers")
        ),
        sa.ForeignKeyConstraint(
            ["subscription_id"],
            ["subscriptions.id"],
            name=op.f("fk_invoices_subscription_id_subscriptions"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_invoices_tenant_id_tenants")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_invoices")),
        sa.UniqueConstraint("public_id", name=op.f("uq_invoices_public_id")),
        sa.UniqueConstraint("tenant_id", "number", name="uq_invoices_tenant_id_number"),
    )
    op.create_index(op.f("ix_invoices_customer_id"), "invoices", ["customer_id"], unique=False)
    op.create_index(
        op.f("ix_invoices_next_payment_attempt"), "invoices", ["next_payment_attempt"], unique=False
    )
    op.create_index(
        op.f("ix_invoices_subscription_id"), "invoices", ["subscription_id"], unique=False
    )
    op.create_index(op.f("ix_invoices_tenant_id"), "invoices", ["tenant_id"], unique=False)

    op.create_table(
        "invoice_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("subscription_id", sa.Integer(), nullable=True),
        sa.Column("invoice_id", sa.Integer(), nullable=True),
        sa.Column("price_id", sa.Integer(), nullable=True),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("proration", sa.Boolean(), nullable=False),
        sa.Column("period_start", sa.DateTime(), nullable=True),
        sa.Column("period_end", sa.DateTime(), nullable=True),
        *_timestamps(),
        sa.Column("public_id", sa.String(length=40), nullable=False),
        sa.ForeignKeyConstraint(
            ["customer_id"], ["customers.id"], name=op.f("fk_invoice_items_customer_id_customers")
        ),
        sa.ForeignKeyConstraint(
            ["invoice_id"], ["invoices.id"], name=op.f("fk_invoice_items_invoice_id_invoices")
        ),
        sa.ForeignKeyConstraint(
            ["price_id"], ["prices.id"], name=op.f("fk_invoice_items_price_id_prices")
        ),
        sa.ForeignKeyConstraint(
            ["subscription_id"],
            ["subscriptions.id"],
            name=op.f("fk_invoice_items_subscription_id_subscriptions"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_invoice_items_tenant_id_tenants")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_invoice_items")),
        sa.UniqueConstraint("public_id", name=op.f("uq_invoice_items_public_id")),
    )
    op.create_index(
        op.f("ix_invoice_items_customer_id"), "invoice_items", ["customer_id"], unique=False
    )
    op.create_index(
        op.f("ix_invoice_items_invoice_id"), "invoice_items", ["invoice_id"], unique=False
    )
    op.create_index(
        op.f("ix_invoice_items_subscription_id"), "invoice_items", ["subscription_id"], unique=False
    )
    op.create_index(
        op.f("ix_invoice_items_tenant_id"), "invoice_items", ["tenant_id"], unique=False
    )

    op.create_table(
        "invoice_lines",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("invoice_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("line_type", sa.String(length=20), nullable=False),
        sa.Column("subscription_item_id", sa.Integer(), nullable=True),
        sa.Column("invoice_item_id", sa.Integer(), nullable=True),
        sa.Column("price_id", sa.Integer(), nullable=True),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("proration", sa.Boolean(), nullable=False),
        sa.Column("period_start", sa.DateTime(), nullable=True),
        sa.Column("period_end", sa.DateTime(), nullable=True),
        sa.Column("public_id", sa.String(length=40), nullable=False),
        sa.ForeignKeyConstraint(
            ["invoice_id"], ["invoices.id"], name=op.f("fk_invoice_lines_invoice_id_invoices")
        ),
        sa.ForeignKeyConstraint(
            ["invoice_item_id"],
            ["invoice_items.id"],
            name=op.f("fk_invoice_lines_invoice_item_id_invoice_items"),
        ),
        sa.ForeignKeyConstraint(
            ["price_id"], ["prices.id"], name=op.f("fk_invoice_lines_price_id_prices")
        ),
        sa.ForeignKeyConstraint(
            ["subscription_item_id"],
            ["subscription_items.id"],
            name=op.f("fk_invoice_lines_subscription_item_id_subscription_items"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_invoice_lines")),
        sa.UniqueConstraint("public_id", name=op.f("uq_invoice_lines_public_id")),
    )
    op.create_index(
        op.f("ix_invoice_lines_invoice_id"), "invoice_lines", ["invoice_id"], unique=False
    )

    op.create_table(
        "payment_attempts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("invoice_id", sa.Integer(), nullable=False),
        sa.Column("payment_method_id", sa.Integer(), nullable=True),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("failure_code", sa.String(length=50), nullable=True),
        sa.Column("failure_message", sa.String(length=255), nullable=True),
        sa.Column("gateway_reference", sa.String(length=64), nullable=True),
        sa.Column("idempotency_key", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("public_id", sa.String(length=40), nullable=False),
        sa.ForeignKeyConstraint(
            ["invoice_id"], ["invoices.id"], name=op.f("fk_payment_attempts_invoice_id_invoices")
        ),
        sa.ForeignKeyConstraint(
            ["payment_method_id"],
            ["payment_methods.id"],
            name=op.f("fk_payment_attempts_payment_method_id_payment_methods"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_payment_attempts_tenant_id_tenants")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_payment_attempts")),
        sa.UniqueConstraint("public_id", name=op.f("uq_payment_attempts_public_id")),
    )
    op.create_index(
        op.f("ix_payment_attempts_invoice_id"), "payment_attempts", ["invoice_id"], unique=False
    )
    op.create_index(
        op.f("ix_payment_attempts_tenant_id"), "payment_attempts", ["tenant_id"], unique=False
    )


def downgrade():
    op.drop_table("payment_attempts")
    op.drop_table("invoice_lines")
    op.drop_table("invoice_items")
    op.drop_table("invoices")
    op.drop_table("subscription_items")
    op.drop_table("subscriptions")
    op.drop_table("prices")
    op.drop_table("products")
    op.drop_table("payment_methods")
    op.drop_table("customers")
    op.drop_table("api_keys")
    op.drop_table("tenants")
