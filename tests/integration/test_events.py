import calendar
import json
from datetime import timedelta

from ledgerline.events import webhooks
from ledgerline.models import Event, WebhookDelivery
from tests.support import factories


def test_publish_creates_deliveries_for_subscribed_endpoints(db, tenant):
    everything = factories.webhook_endpoint(tenant, events=["*"])
    paid_only = factories.webhook_endpoint(tenant, events=["invoice.paid"])
    factories.subscribe(factories.customer(tenant), factories.price(tenant))
    db.session.commit()

    types = [event.type for event in Event.query.order_by(Event.id)]
    assert types == [
        "customer.subscription.created",
        "invoice.finalized",
        "customer.subscription.updated",
        "invoice.paid",
    ]
    by_endpoint = {}
    for delivery in WebhookDelivery.query.all():
        by_endpoint.setdefault(delivery.endpoint_id, []).append(delivery.event.type)
    assert len(by_endpoint[everything.id]) == len(types)
    assert by_endpoint[paid_only.id] == ["invoice.paid"]


def test_events_roll_back_with_the_transaction(db, tenant):
    factories.webhook_endpoint(tenant)
    factories.subscribe(factories.customer(tenant), factories.price(tenant))
    db.session.rollback()
    assert Event.query.count() == 0
    assert WebhookDelivery.query.count() == 0


def test_event_payload_is_a_snapshot(db, tenant):
    factories.subscribe(factories.customer(tenant), factories.price(tenant))
    finalized = Event.query.filter_by(type="invoice.finalized").one()
    paid = Event.query.filter_by(type="invoice.paid").one()
    assert finalized.payload["object"]["status"] == "open"
    assert paid.payload["object"]["status"] == "paid"


def test_dispatch_signs_and_delivers(db, tenant, transport, clock):
    endpoint = factories.webhook_endpoint(tenant, events=["invoice.paid"])
    factories.subscribe(factories.customer(tenant), factories.price(tenant))
    db.session.commit()

    summary = webhooks.dispatch_due(transport=transport)
    assert summary == {"attempted": 1, "succeeded": 1, "failed": 0}
    [request] = transport.requests
    assert request["url"] == endpoint.url
    body = json.loads(request["body"])
    assert body["type"] == "invoice.paid"
    assert body["data"]["object"]["object"] == "invoice"
    now = calendar.timegm(clock.now().utctimetuple())
    assert webhooks.verify_signature(
        request["headers"][webhooks.SIGNATURE_HEADER], endpoint.secret, request["body"], now
    )
    delivery = WebhookDelivery.query.one()
    assert delivery.status == "succeeded"
    assert delivery.response_status == 200


def test_failed_delivery_is_retried_with_backoff(db, tenant, transport, clock):
    factories.webhook_endpoint(tenant, events=["invoice.paid"])
    factories.subscribe(factories.customer(tenant), factories.price(tenant))
    db.session.commit()
    transport.statuses = [500, 503, 200]

    webhooks.dispatch_due(transport=transport)
    delivery = WebhookDelivery.query.one()
    assert delivery.status == "pending"
    assert delivery.attempt_count == 1
    assert delivery.next_attempt_at == clock.now() + timedelta(minutes=1)
    assert delivery.last_error == "HTTP 500"

    assert webhooks.dispatch_due(transport=transport)["attempted"] == 0
    clock.advance(minutes=1)
    webhooks.dispatch_due(transport=transport)
    assert delivery.attempt_count == 2
    assert delivery.next_attempt_at == clock.now() + timedelta(minutes=2)

    clock.advance(minutes=2)
    webhooks.dispatch_due(transport=transport)
    assert delivery.status == "succeeded"
    assert len(transport.requests) == 3


def test_delivery_gives_up_after_max_attempts(app, db, tenant, transport, clock):
    app.config["LEDGERLINE_WEBHOOK_MAX_ATTEMPTS"] = 2
    factories.webhook_endpoint(tenant, events=["invoice.paid"])
    factories.subscribe(factories.customer(tenant), factories.price(tenant))
    db.session.commit()
    transport.statuses = [500, 500]
    webhooks.dispatch_due(transport=transport)
    clock.advance(minutes=1)
    webhooks.dispatch_due(transport=transport)
    delivery = WebhookDelivery.query.one()
    assert delivery.status == "failed"
    assert delivery.next_attempt_at is None


def test_inactive_endpoints_receive_nothing(db, tenant):
    endpoint = factories.webhook_endpoint(tenant)
    endpoint.active = False
    factories.subscribe(factories.customer(tenant), factories.price(tenant))
    assert WebhookDelivery.query.count() == 0
