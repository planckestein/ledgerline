from ledgerline.extensions import db
from ledgerline.models.base import PublicIdMixin, TimestampMixin, utcnow


class PaymentMethod(PublicIdMixin, TimestampMixin, db.Model):
    __tablename__ = "payment_methods"
    __public_id_prefix__ = "pm"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False, index=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"), nullable=False, index=True)
    type = db.Column(db.String(20), nullable=False, default="card")
    card_brand = db.Column(db.String(20), nullable=True)
    card_last4 = db.Column(db.String(4), nullable=True)
    token = db.Column(db.String(64), nullable=False)
    is_default = db.Column(db.Boolean, nullable=False, default=False)
    detached_at = db.Column(db.DateTime, nullable=True)

    customer = db.relationship("Customer", back_populates="payment_methods")


class PaymentAttempt(PublicIdMixin, db.Model):
    __tablename__ = "payment_attempts"
    __public_id_prefix__ = "pa"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False, index=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey("invoices.id"), nullable=False, index=True)
    payment_method_id = db.Column(db.Integer, db.ForeignKey("payment_methods.id"), nullable=True)
    amount = db.Column(db.Integer, nullable=False)
    currency = db.Column(db.String(3), nullable=False)
    status = db.Column(db.String(20), nullable=False)  # "succeeded" | "failed"
    failure_code = db.Column(db.String(50), nullable=True)
    failure_message = db.Column(db.String(255), nullable=True)
    gateway_reference = db.Column(db.String(64), nullable=True)
    idempotency_key = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    invoice = db.relationship("Invoice", back_populates="payment_attempts")
    payment_method = db.relationship("PaymentMethod")
