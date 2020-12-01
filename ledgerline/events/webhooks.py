"""Webhook signing and delivery.

Each request carries ``Ledgerline-Signature: t=<unix>,v1=<hex>`` where ``v1``
is ``HMAC-SHA256(secret, "<t>.<raw body>")``. Receivers should reject
signatures older than five minutes.

Failed deliveries are retried with exponential backoff (1 min, 2 min, 4 min,
... capped at 6 hours) until ``LEDGERLINE_WEBHOOK_MAX_ATTEMPTS`` is reached.
"""
import calendar
import hashlib
import hmac
import json
import logging
import secrets
from datetime import timedelta

import requests
from flask import current_app

from ledgerline import clock
from ledgerline.extensions import db
from ledgerline.models import WebhookDelivery

log = logging.getLogger(__name__)

SIGNATURE_HEADER = "Ledgerline-Signature"
MAX_BACKOFF = timedelta(hours=6)


def generate_secret():
    return "whsec_" + secrets.token_hex(24)


def compute_signature(secret, timestamp, body):
    message = ("%d.%s" % (timestamp, body)).encode("utf-8")
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


def signature_header(secret, timestamp, body):
    return "t=%d,v1=%s" % (timestamp, compute_signature(secret, timestamp, body))


def verify_signature(header, secret, body, now_timestamp, tolerance=300):
    """Verify a signature header the way a receiver would."""
    try:
        parts = dict(item.split("=", 1) for item in header.split(","))
        timestamp = int(parts["t"])
        signature = parts["v1"]
    except (KeyError, ValueError):
        return False
    if abs(now_timestamp - timestamp) > tolerance:
        return False
    expected = compute_signature(secret, timestamp, body)
    return hmac.compare_digest(expected, signature)


def backoff(attempt_count):
    """Delay before the next attempt after ``attempt_count`` failed attempts."""
    delay = timedelta(minutes=2 ** max(attempt_count - 1, 0))
    return min(delay, MAX_BACKOFF)


class RequestsTransport:
    def __init__(self, session=None):
        self.session = session or requests.Session()

    def post(self, url, body, headers, timeout):
        response = self.session.post(url, data=body, headers=headers, timeout=timeout)
        return response.status_code


def _render(delivery):
    event = delivery.event
    return json.dumps(
        {
            "id": event.public_id,
            "object": "event",
            "type": event.type,
            "created": calendar.timegm(event.created_at.utctimetuple()),
            "data": event.payload,
        },
        sort_keys=True,
    )


def deliver(delivery, transport, now):
    body = _render(delivery)
    timestamp = calendar.timegm(now.utctimetuple())
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Ledgerline-Webhooks/1.0",
        SIGNATURE_HEADER: signature_header(delivery.endpoint.secret, timestamp, body),
    }
    delivery.attempt_count += 1
    delivery.last_attempt_at = now
    try:
        status = transport.post(
            delivery.endpoint.url, body, headers, current_app.config["LEDGERLINE_WEBHOOK_TIMEOUT"]
        )
    except requests.RequestException as exc:
        # Unreachable endpoints (DNS failures, refused connections, timeouts)
        # are retried like any other failed delivery.
        log.info("Webhook delivery %s failed: %s", delivery.id, exc)
        delivery.response_status = None
        _schedule_retry(delivery, now, "%s: %s" % (type(exc).__name__, exc))
        return False
    delivery.response_status = status
    if 200 <= status < 300:
        delivery.status = "succeeded"
        delivery.next_attempt_at = None
        delivery.last_error = None
        return True
    _schedule_retry(delivery, now, "HTTP %d" % status)
    return False


def _schedule_retry(delivery, now, error):
    delivery.last_error = error[:500]
    if delivery.attempt_count >= current_app.config["LEDGERLINE_WEBHOOK_MAX_ATTEMPTS"]:
        delivery.status = "failed"
        delivery.next_attempt_at = None
    else:
        delivery.next_attempt_at = now + backoff(delivery.attempt_count)


def dispatch_due(transport=None, now=None, limit=100):
    """Send every pending delivery whose next attempt is due."""
    transport = transport or RequestsTransport()
    now = now or clock.utcnow()
    deliveries = (
        WebhookDelivery.query.filter(
            WebhookDelivery.status == "pending",
            WebhookDelivery.next_attempt_at <= now,
        )
        .order_by(WebhookDelivery.next_attempt_at, WebhookDelivery.id)
        .limit(limit)
        .all()
    )
    summary = {"attempted": 0, "succeeded": 0, "failed": 0}
    for delivery in deliveries:
        ok = deliver(delivery, transport, now)
        summary["attempted"] += 1
        summary["succeeded" if ok else "failed"] += 1
        db.session.commit()
    return summary
