from ledgerline.extensions import db
from ledgerline.models.base import PublicIdMixin, TimestampMixin

INVOICE_STATUSES = ("draft", "open", "paid", "void", "uncollectible")
BILLING_REASONS = (
    "subscription_create",
    "subscription_cycle",
    "subscription_update",
    "subscription_cancel",
    "manual",
)


class Invoice(PublicIdMixin, TimestampMixin, db.Model):
    """An invoice. All amounts are integers in minor units of ``currency``.

    Invariants once finalized (see docs/billing-model.md):

    * ``subtotal == sum(line.amount)``
    * ``total == subtotal``
    """

    __tablename__ = "invoices"
    __public_id_prefix__ = "in"
    __table_args__ = (
        db.UniqueConstraint("tenant_id", "number", name="uq_invoices_tenant_id_number"),
    )

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False, index=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"), nullable=False, index=True)
    subscription_id = db.Column(
        db.Integer, db.ForeignKey("subscriptions.id"), nullable=True, index=True
    )
    number = db.Column(db.String(40), nullable=True)
    status = db.Column(db.String(20), nullable=False, default="draft")
    billing_reason = db.Column(db.String(30), nullable=False, default="manual")
    collection_method = db.Column(db.String(30), nullable=False, default="charge_automatically")
    days_until_due = db.Column(db.Integer, nullable=True)
    currency = db.Column(db.String(3), nullable=False)
    period_start = db.Column(db.DateTime, nullable=True)
    period_end = db.Column(db.DateTime, nullable=True)

    subtotal = db.Column(db.Integer, nullable=False, default=0)
    total = db.Column(db.Integer, nullable=False, default=0)
    amount_due = db.Column(db.Integer, nullable=False, default=0)
    amount_paid = db.Column(db.Integer, nullable=False, default=0)

    attempt_count = db.Column(db.Integer, nullable=False, default=0)
    next_payment_attempt = db.Column(db.DateTime, nullable=True, index=True)
    due_date = db.Column(db.DateTime, nullable=True)
    finalized_at = db.Column(db.DateTime, nullable=True)
    paid_at = db.Column(db.DateTime, nullable=True)
    voided_at = db.Column(db.DateTime, nullable=True)
    marked_uncollectible_at = db.Column(db.DateTime, nullable=True)

    customer = db.relationship("Customer")
    subscription = db.relationship("Subscription")
    lines = db.relationship(
        "InvoiceLine",
        back_populates="invoice",
        order_by="InvoiceLine.position",
        cascade="all, delete-orphan",
    )
    payment_attempts = db.relationship(
        "PaymentAttempt", back_populates="invoice", order_by="PaymentAttempt.id"
    )


class InvoiceLine(PublicIdMixin, db.Model):
    __tablename__ = "invoice_lines"
    __public_id_prefix__ = "il"

    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey("invoices.id"), nullable=False, index=True)
    position = db.Column(db.Integer, nullable=False)
    line_type = db.Column(db.String(20), nullable=False)  # "subscription" | "invoiceitem"
    subscription_item_id = db.Column(
        db.Integer, db.ForeignKey("subscription_items.id"), nullable=True
    )
    invoice_item_id = db.Column(db.Integer, db.ForeignKey("invoice_items.id"), nullable=True)
    price_id = db.Column(db.Integer, db.ForeignKey("prices.id"), nullable=True)
    description = db.Column(db.String(500), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    amount = db.Column(db.Integer, nullable=False)
    proration = db.Column(db.Boolean, nullable=False, default=False)
    period_start = db.Column(db.DateTime, nullable=True)
    period_end = db.Column(db.DateTime, nullable=True)

    invoice = db.relationship("Invoice", back_populates="lines")
    price = db.relationship("Price")
    subscription_item = db.relationship("SubscriptionItem")


class InvoiceItem(PublicIdMixin, TimestampMixin, db.Model):
    """A pending charge or credit that will be pulled into the customer's next invoice.

    Prorations are stored as invoice items with ``proration=True``.
    """

    __tablename__ = "invoice_items"
    __public_id_prefix__ = "ii"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False, index=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"), nullable=False, index=True)
    subscription_id = db.Column(
        db.Integer, db.ForeignKey("subscriptions.id"), nullable=True, index=True
    )
    invoice_id = db.Column(db.Integer, db.ForeignKey("invoices.id"), nullable=True, index=True)
    price_id = db.Column(db.Integer, db.ForeignKey("prices.id"), nullable=True)
    description = db.Column(db.String(500), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    amount = db.Column(db.Integer, nullable=False)
    currency = db.Column(db.String(3), nullable=False)
    proration = db.Column(db.Boolean, nullable=False, default=False)
    period_start = db.Column(db.DateTime, nullable=True)
    period_end = db.Column(db.DateTime, nullable=True)

    customer = db.relationship("Customer")
    subscription = db.relationship("Subscription")
    invoice = db.relationship("Invoice")
    price = db.relationship("Price")
