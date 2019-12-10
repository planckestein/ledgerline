"""API key authentication: ``Authorization: Bearer sk_test_...``."""
from flask import g, request

from ledgerline.api import api_bp
from ledgerline.errors import AuthenticationError
from ledgerline.extensions import db
from ledgerline.models import ApiKey, Tenant


def authenticate():
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        raise AuthenticationError(
            "No API key provided. Use 'Authorization: Bearer <secret key>'.",
            code="missing_api_key",
        )
    secret = header[len("Bearer ") :].strip()
    row = (
        db.session.query(ApiKey, Tenant)
        .join(Tenant, Tenant.id == ApiKey.tenant_id)
        .filter(ApiKey.key_hash == ApiKey.hash_secret(secret), ApiKey.revoked_at.is_(None))
        .first()
    )
    if row is None:
        raise AuthenticationError("Invalid API key provided.", code="invalid_api_key")
    g.api_key, g.tenant = row


@api_bp.before_request
def _authenticate_request():
    authenticate()
