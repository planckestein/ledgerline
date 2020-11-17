"""``Idempotency-Key`` support for mutating endpoints.

* The first request with a key is executed and its response stored.
* Retries with the same key and the same parameters replay the stored
  response with ``Idempotent-Replayed: true``.
* Reusing a key with different parameters is rejected (422).
* A retry that arrives while the first request is still running gets 409.
* 5xx responses are not stored, so the request can be retried safely.
* Keys expire after ``LEDGERLINE_IDEMPOTENCY_TTL`` seconds.
"""
import functools
import hashlib
import json
from datetime import timedelta

from flask import current_app, g, make_response, request
from sqlalchemy.exc import IntegrityError

from ledgerline import clock
from ledgerline.api.errors import error_response
from ledgerline.errors import ConflictError, IdempotencyError, InvalidRequestError, LedgerlineError
from ledgerline.extensions import db
from ledgerline.models import IdempotencyKey

HEADER = "Idempotency-Key"
MAX_KEY_LENGTH = 255


def request_fingerprint():
    raw = request.get_data(cache=True)
    try:
        canonical = json.dumps(json.loads(raw.decode("utf-8")), sort_keys=True) if raw else ""
    except ValueError:
        canonical = raw.decode("utf-8", "replace")
    material = "%s %s\n%s" % (request.method, request.path, canonical)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def find_key(tenant_id, key):
    # Look the key up through its fixed-width hash, which is backed by a
    # compact unique index (see migration f3b9d2e6a399).
    return IdempotencyKey.query.filter_by(key_hash=IdempotencyKey.hash_key(key)).first()


def _expired(record, now):
    ttl = current_app.config["LEDGERLINE_IDEMPOTENCY_TTL"]
    return record.created_at <= now - timedelta(seconds=ttl)


def _replay(record):
    response = current_app.response_class(
        record.response_body, status=record.response_status, mimetype="application/json"
    )
    response.headers["Idempotent-Replayed"] = "true"
    return response


def _delete(record_id):
    IdempotencyKey.query.filter_by(id=record_id).delete()
    db.session.commit()


def idempotent(view):
    @functools.wraps(view)
    def wrapper(*args, **kwargs):
        key = request.headers.get(HEADER)
        if key is None:
            return view(*args, **kwargs)
        key = key.strip()
        if not key or len(key) > MAX_KEY_LENGTH:
            raise InvalidRequestError(
                "Idempotency-Key must be between 1 and %d characters" % MAX_KEY_LENGTH,
                param=HEADER,
            )

        now = clock.utcnow()
        fingerprint = request_fingerprint()
        record = find_key(g.tenant.id, key)
        if record is not None and _expired(record, now):
            db.session.delete(record)
            db.session.commit()
            record = None

        if record is not None:
            if record.request_fingerprint != fingerprint:
                raise IdempotencyError(
                    "Keys for idempotent requests can only be used with the same parameters "
                    "they were first used with. Try using a key other than '%s' if you meant "
                    "to execute a different request." % key
                )
            if record.response_status is None:
                raise ConflictError(
                    "A request with this Idempotency-Key is still being processed.",
                    code="idempotency_key_in_use",
                )
            return _replay(record)

        record = IdempotencyKey(
            tenant_id=g.tenant.id,
            key=key,
            key_hash=IdempotencyKey.hash_key(key),
            request_method=request.method,
            request_path=request.path,
            request_fingerprint=fingerprint,
            locked_at=now,
            created_at=now,
        )
        db.session.add(record)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            raise ConflictError(
                "A request with this Idempotency-Key is still being processed.",
                code="idempotency_key_in_use",
            )
        record_id = record.id

        try:
            response = make_response(view(*args, **kwargs))
        except LedgerlineError as exc:
            db.session.rollback()
            response = error_response(exc)
        except Exception:
            db.session.rollback()
            _delete(record_id)
            raise

        if response.status_code >= 500:
            _delete(record_id)
            return response

        record = IdempotencyKey.query.get(record_id)
        record.response_status = response.status_code
        record.response_body = response.get_data(as_text=True)
        record.locked_at = None
        db.session.commit()
        return response

    return wrapper


def purge_expired(now=None):
    now = now or clock.utcnow()
    cutoff = now - timedelta(seconds=current_app.config["LEDGERLINE_IDEMPOTENCY_TTL"])
    deleted = IdempotencyKey.query.filter(IdempotencyKey.created_at <= cutoff).delete(
        synchronize_session=False
    )
    db.session.commit()
    return deleted
