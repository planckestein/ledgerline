from ledgerline.extensions import db
from ledgerline.models.base import PublicIdMixin, TimestampMixin


class TaxRate(PublicIdMixin, TimestampMixin, db.Model):
    """A tax rate. ``country``/``state`` NULL means "applies everywhere"."""

    __tablename__ = "tax_rates"
    __public_id_prefix__ = "txr"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False, index=True)
    display_name = db.Column(db.String(100), nullable=False)
    percentage = db.Column(db.Numeric(7, 4), nullable=False)
    inclusive = db.Column(db.Boolean, nullable=False, default=False)
    country = db.Column(db.String(2), nullable=True)
    state = db.Column(db.String(10), nullable=True)
    active = db.Column(db.Boolean, nullable=False, default=True)
