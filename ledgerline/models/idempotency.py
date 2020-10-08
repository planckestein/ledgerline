from ledgerline.extensions import db
from ledgerline.models.base import utcnow


class IdempotencyKey(db.Model):
    """Stored responses for requests sent with an ``Idempotency-Key`` header.

    Keys are chosen by API clients, so they are only unique *per tenant*.
    """

    __tablename__ = "idempotency_keys"
    __table_args__ = (
        db.UniqueConstraint("tenant_id", "key", name="uq_idempotency_keys_tenant_id_key"),
    )

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False, index=True)
    key = db.Column(db.String(255), nullable=False)
    request_method = db.Column(db.String(10), nullable=False)
    request_path = db.Column(db.String(255), nullable=False)
    request_fingerprint = db.Column(db.String(64), nullable=False)
    response_status = db.Column(db.Integer, nullable=True)
    response_body = db.Column(db.Text, nullable=True)
    locked_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)
