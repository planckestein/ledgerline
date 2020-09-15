"""Domain events (transactional outbox).

``publish`` writes an :class:`~ledgerline.models.Event` plus one pending
:class:`~ledgerline.models.WebhookDelivery` per subscribed endpoint *in the
current transaction*. If the business transaction rolls back, so do its
events; nothing is sent until the dispatcher picks deliveries up.
"""
from ledgerline import clock
from ledgerline.extensions import db
from ledgerline.models import Event, WebhookDelivery, WebhookEndpoint

EVENT_TYPES = (
    "customer.created",
    "customer.updated",
    "customer.subscription.created",
    "customer.subscription.updated",
    "customer.subscription.deleted",
    "invoice.created",
    "invoice.finalized",
    "invoice.paid",
    "invoice.payment_failed",
    "invoice.voided",
    "invoice.marked_uncollectible",
)


def publish(event_type, obj):
    """Publish ``event_type`` with a snapshot of ``obj`` taken now."""
    from ledgerline.serializers import serialize

    if event_type not in EVENT_TYPES:
        raise ValueError("Unknown event type %r" % (event_type,))
    db.session.flush()
    now = clock.utcnow()
    event = Event(
        tenant_id=obj.tenant_id,
        type=event_type,
        payload={"object": serialize(obj)},
        created_at=now,
    )
    db.session.add(event)

    endpoints = WebhookEndpoint.query.filter_by(tenant_id=obj.tenant_id, active=True).all()
    for endpoint in endpoints:
        if endpoint.accepts(event_type):
            db.session.add(
                WebhookDelivery(
                    event=event, endpoint=endpoint, status="pending", next_attempt_at=now
                )
            )
    return event
