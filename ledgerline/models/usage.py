from ledgerline.extensions import db
from ledgerline.models.base import PublicIdMixin, utcnow


class UsageRecord(PublicIdMixin, db.Model):
    __tablename__ = "usage_records"
    __public_id_prefix__ = "mbur"

    id = db.Column(db.Integer, primary_key=True)
    subscription_item_id = db.Column(
        db.Integer, db.ForeignKey("subscription_items.id"), nullable=False, index=True
    )
    quantity = db.Column(db.Integer, nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    subscription_item = db.relationship("SubscriptionItem")
