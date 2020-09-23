"""/v1/webhook_endpoints and /v1/events"""
from flask import g, jsonify, request

from ledgerline.api import api_bp
from ledgerline.api.helpers import get_or_404, load, scoped
from ledgerline.api.pagination import paginate
from ledgerline.api.schemas import WebhookEndpointSchema, WebhookEndpointUpdateSchema
from ledgerline.events.webhooks import generate_secret
from ledgerline.extensions import db
from ledgerline.models import Event, WebhookEndpoint
from ledgerline.serializers import serialize_event, serialize_webhook_endpoint


@api_bp.route("/webhook_endpoints", methods=["POST"])
def create_webhook_endpoint():
    data = load(WebhookEndpointSchema())
    endpoint = WebhookEndpoint(
        tenant_id=g.tenant.id,
        url=data["url"],
        enabled_events=sorted(set(data["enabled_events"])),
        secret=generate_secret(),
        active=True,
    )
    db.session.add(endpoint)
    db.session.commit()
    return jsonify(serialize_webhook_endpoint(endpoint, include_secret=True)), 201


@api_bp.route("/webhook_endpoints", methods=["GET"])
def list_webhook_endpoints():
    return jsonify(paginate(scoped(WebhookEndpoint), WebhookEndpoint, serialize_webhook_endpoint))


@api_bp.route("/webhook_endpoints/<endpoint_id>", methods=["GET"])
def get_webhook_endpoint(endpoint_id):
    return jsonify(serialize_webhook_endpoint(get_or_404(WebhookEndpoint, endpoint_id)))


@api_bp.route("/webhook_endpoints/<endpoint_id>", methods=["POST"])
def update_webhook_endpoint(endpoint_id):
    endpoint = get_or_404(WebhookEndpoint, endpoint_id)
    data = load(WebhookEndpointUpdateSchema())
    if "enabled_events" in data:
        data["enabled_events"] = sorted(set(data["enabled_events"]))
    for key, value in data.items():
        setattr(endpoint, key, value)
    db.session.commit()
    return jsonify(serialize_webhook_endpoint(endpoint))


@api_bp.route("/events", methods=["GET"])
def list_events():
    query = scoped(Event)
    if request.args.get("type"):
        query = query.filter(Event.type == request.args["type"])
    return jsonify(paginate(query, Event, serialize_event))


@api_bp.route("/events/<event_id>", methods=["GET"])
def get_event(event_id):
    return jsonify(serialize_event(get_or_404(Event, event_id)))
