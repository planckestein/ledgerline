from ledgerline.extensions import db
from ledgerline.models.base import PublicIdMixin, TimestampMixin

SUBSCRIPTION_STATUSES = ("incomplete", "trialing", "active", "past_due", "unpaid", "canceled")
BILLABLE_STATUSES = ("trialing", "active", "past_due")


class Subscription(PublicIdMixin, TimestampMixin, db.Model):
    """A customer's recurring subscription to one or more prices.

    ``billing_cycle_anchor`` is the reference instant that determines where
    every period boundary falls (see docs/billing-model.md, "Billing periods").
    """

    __tablename__ = "subscriptions"
    __public_id_prefix__ = "sub"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False, index=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"), nullable=False, index=True)
    status = db.Column(db.String(20), nullable=False)
    collection_method = db.Column(db.String(30), nullable=False, default="charge_automatically")
    days_until_due = db.Column(db.Integer, nullable=True)
    billing_cycle_anchor = db.Column(db.DateTime, nullable=False)
    current_period_start = db.Column(db.DateTime, nullable=False)
    current_period_end = db.Column(db.DateTime, nullable=False, index=True)
    trial_start = db.Column(db.DateTime, nullable=True)
    trial_end = db.Column(db.DateTime, nullable=True)
    cancel_at_period_end = db.Column(db.Boolean, nullable=False, default=False)
    canceled_at = db.Column(db.DateTime, nullable=True)
    ended_at = db.Column(db.DateTime, nullable=True)

    customer = db.relationship("Customer")
    items = db.relationship(
        "SubscriptionItem", back_populates="subscription", order_by="SubscriptionItem.id"
    )

    @property
    def active_items(self):
        return [item for item in self.items if item.deleted_at is None]

    @property
    def primary_price(self):
        items = self.active_items
        return items[0].price if items else None

    @property
    def currency(self):
        price = self.primary_price
        return price.currency if price else None

    @property
    def interval(self):
        price = self.primary_price
        return (price.interval, price.interval_count) if price else None


class SubscriptionItem(PublicIdMixin, TimestampMixin, db.Model):
    __tablename__ = "subscription_items"
    __public_id_prefix__ = "si"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False, index=True)
    subscription_id = db.Column(
        db.Integer, db.ForeignKey("subscriptions.id"), nullable=False, index=True
    )
    price_id = db.Column(db.Integer, db.ForeignKey("prices.id"), nullable=False, index=True)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    # Items are soft-deleted because invoice lines and usage records reference them.
    deleted_at = db.Column(db.DateTime, nullable=True)

    subscription = db.relationship("Subscription", back_populates="items")
    price = db.relationship("Price")
