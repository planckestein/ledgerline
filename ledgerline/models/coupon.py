from ledgerline.extensions import db
from ledgerline.models.base import PublicIdMixin, TimestampMixin, utcnow

COUPON_DURATIONS = ("once", "repeating", "forever")


class Coupon(PublicIdMixin, TimestampMixin, db.Model):
    """Either ``percent_off`` or ``amount_off`` (+ ``currency``) is set, never both."""

    __tablename__ = "coupons"
    __public_id_prefix__ = "co"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False, index=True)
    name = db.Column(db.String(200), nullable=True)
    percent_off = db.Column(db.Numeric(6, 3), nullable=True)
    amount_off = db.Column(db.Integer, nullable=True)
    currency = db.Column(db.String(3), nullable=True)
    duration = db.Column(db.String(20), nullable=False)
    duration_in_months = db.Column(db.Integer, nullable=True)
    max_redemptions = db.Column(db.Integer, nullable=True)
    times_redeemed = db.Column(db.Integer, nullable=False, default=0)
    valid = db.Column(db.Boolean, nullable=False, default=True)


class Discount(PublicIdMixin, db.Model):
    """A coupon applied to a customer (``subscription_id`` NULL) or to one subscription.

    A discount is active for invoices whose reference time falls in
    ``[start, end)``; ``end`` is NULL for ``forever`` coupons and for ``once``
    coupons that have not been used yet.
    """

    __tablename__ = "discounts"
    __public_id_prefix__ = "di"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False, index=True)
    coupon_id = db.Column(db.Integer, db.ForeignKey("coupons.id"), nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"), nullable=False, index=True)
    subscription_id = db.Column(
        db.Integer, db.ForeignKey("subscriptions.id"), nullable=True, index=True
    )
    start = db.Column(db.DateTime, nullable=False)
    end = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    coupon = db.relationship("Coupon")
    customer = db.relationship("Customer")
    subscription = db.relationship("Subscription")
