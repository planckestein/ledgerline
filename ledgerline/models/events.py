from ledgerline.extensions import db
from ledgerline.models.base import JSONText, PublicIdMixin, TimestampMixin, utcnow


class Event(PublicIdMixin, db.Model):
    """Transactional outbox: written in the same transaction as the state change."""

    __tablename__ = "events"
    __public_id_prefix__ = "evt"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False, index=True)
    type = db.Column(db.String(60), nullable=False, index=True)
    payload = db.Column(JSONText, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)


class WebhookEndpoint(PublicIdMixin, TimestampMixin, db.Model):
    __tablename__ = "webhook_endpoints"
    __public_id_prefix__ = "we"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False, index=True)
    url = db.Column(db.String(500), nullable=False)
    secret = db.Column(db.String(64), nullable=False)
    enabled_events = db.Column(JSONText, nullable=False)
    active = db.Column(db.Boolean, nullable=False, default=True)

    def accepts(self, event_type):
        events = self.enabled_events or []
        return "*" in events or event_type in events


class WebhookDelivery(db.Model):
    __tablename__ = "webhook_deliveries"

    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey("events.id"), nullable=False, index=True)
    endpoint_id = db.Column(
        db.Integer, db.ForeignKey("webhook_endpoints.id"), nullable=False, index=True
    )
    status = db.Column(db.String(20), nullable=False, default="pending")
    attempt_count = db.Column(db.Integer, nullable=False, default=0)
    next_attempt_at = db.Column(db.DateTime, nullable=True, index=True)
    last_attempt_at = db.Column(db.DateTime, nullable=True)
    response_status = db.Column(db.Integer, nullable=True)
    last_error = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    event = db.relationship("Event")
    endpoint = db.relationship("WebhookEndpoint")
