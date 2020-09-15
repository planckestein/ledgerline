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


def test_inactive_endpoints_receive_nothing(db, tenant):
    endpoint = factories.webhook_endpoint(tenant)
    endpoint.active = False
    factories.subscribe(factories.customer(tenant), factories.price(tenant))
    assert WebhookDelivery.query.count() == 0
