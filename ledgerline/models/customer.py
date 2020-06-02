import secrets
import string

from ledgerline.extensions import db
from ledgerline.geo import parse_legacy_address
from ledgerline.models.base import JSONText, PublicIdMixin, TimestampMixin

_PREFIX_ALPHABET = string.ascii_uppercase + string.digits


def generate_invoice_prefix():
    return "".join(secrets.choice(_PREFIX_ALPHABET) for _ in range(8))


class Customer(PublicIdMixin, TimestampMixin, db.Model):
    __tablename__ = "customers"
    __public_id_prefix__ = "cus"
    __table_args__ = (
        db.UniqueConstraint(
            "tenant_id", "invoice_prefix", name="uq_customers_tenant_id_invoice_prefix"
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False, index=True)
    email = db.Column(db.String(255), nullable=True)
    name = db.Column(db.String(200), nullable=True)
    # Set when the first subscription or invoice item is created; immutable afterwards.
    currency = db.Column(db.String(3), nullable=True)
    # Legacy free-form column, see ledgerline.geo for the formats it may contain.
    billing_address = db.Column(db.Text, nullable=True)
    vat_id = db.Column(db.String(64), nullable=True)
    tax_exempt = db.Column(db.Boolean, nullable=False, default=False)
    invoice_prefix = db.Column(db.String(12), nullable=False, default=generate_invoice_prefix)
    next_invoice_sequence = db.Column(db.Integer, nullable=False, default=1)
    metadata_ = db.Column("metadata", JSONText, nullable=True)

    tenant = db.relationship("Tenant")
    payment_methods = db.relationship(
        "PaymentMethod", back_populates="customer", order_by="PaymentMethod.id"
    )

    @property
    def address(self):
        return parse_legacy_address(self.billing_address)

    @property
    def billing_country(self):
        return self.address["country"]

    @property
    def billing_state(self):
        return self.address["state"]

    @property
    def default_payment_method(self):
        for method in self.payment_methods:
            if method.is_default and method.detached_at is None:
                return method
        return None

    def __repr__(self):
        return "<Customer %s>" % self.public_id
