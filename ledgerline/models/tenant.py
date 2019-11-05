import hashlib
import secrets

from ledgerline.extensions import db
from ledgerline.models.base import PublicIdMixin, TimestampMixin, utcnow


class Tenant(PublicIdMixin, TimestampMixin, db.Model):
    """A merchant account. Every other row belongs to exactly one tenant."""

    __tablename__ = "tenants"
    __public_id_prefix__ = "acct"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    home_country = db.Column(db.String(2), nullable=False)
    default_currency = db.Column(db.String(3), nullable=False)
    # Comma separated list of days to wait between payment retries, e.g. "3,5,7".
    dunning_retry_days = db.Column(db.String(50), nullable=False, default="3,5,7")
    # What happens to a subscription when the last retry fails: "cancel" or "mark_unpaid".
    dunning_final_action = db.Column(db.String(20), nullable=False, default="cancel")

    def __repr__(self):
        return "<Tenant %s %r>" % (self.public_id, self.name)


class ApiKey(db.Model):
    __tablename__ = "api_keys"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False, index=True)
    key_prefix = db.Column(db.String(16), nullable=False)
    key_hash = db.Column(db.String(64), nullable=False, unique=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    revoked_at = db.Column(db.DateTime, nullable=True)

    tenant = db.relationship("Tenant")

    @staticmethod
    def hash_secret(secret):
        return hashlib.sha256(secret.encode("utf-8")).hexdigest()

    @classmethod
    def issue(cls, tenant):
        """Create a new key for ``tenant``. Returns ``(api_key, secret)``.

        Only the SHA-256 of the secret is stored; the secret is shown once.
        """
        secret = "sk_test_" + secrets.token_hex(24)
        key = cls(tenant=tenant, key_prefix=secret[:12], key_hash=cls.hash_secret(secret))
        db.session.add(key)
        return key, secret
