from ledgerline.extensions import db
from ledgerline.models.base import PublicIdMixin, TimestampMixin


class Product(PublicIdMixin, TimestampMixin, db.Model):
    __tablename__ = "products"
    __public_id_prefix__ = "prod"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False, index=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    active = db.Column(db.Boolean, nullable=False, default=True)


class Price(PublicIdMixin, TimestampMixin, db.Model):
    """A recurring price for a product.

    ``unit_amount`` is expressed in minor units of ``currency``.

    * ``billing_scheme="per_unit"``: amount = unit_amount * quantity
    * ``billing_scheme="package"``: amount = ceil(quantity / package_size) * unit_amount
    """

    __tablename__ = "prices"
    __public_id_prefix__ = "price"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False, index=True)
    nickname = db.Column(db.String(200), nullable=True)
    currency = db.Column(db.String(3), nullable=False)
    unit_amount = db.Column(db.Integer, nullable=False)
    billing_scheme = db.Column(db.String(20), nullable=False, default="per_unit")
    package_size = db.Column(db.Integer, nullable=True)
    interval = db.Column(db.String(10), nullable=False)
    interval_count = db.Column(db.Integer, nullable=False, default=1)
    active = db.Column(db.Boolean, nullable=False, default=True)

    product = db.relationship("Product")
