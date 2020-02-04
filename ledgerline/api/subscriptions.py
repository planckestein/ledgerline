"""/v1/subscriptions"""
from flask import jsonify, request

from ledgerline.api import api_bp
from ledgerline.api.helpers import get_or_404, load, scoped
from ledgerline.api.pagination import paginate
from ledgerline.api.schemas import (
    SubscriptionCancelSchema,
    SubscriptionCreateSchema,
    SubscriptionUpdateSchema,
)
from ledgerline.api.serializers import serialize_subscription
from ledgerline.billing import subscriptions as service
from ledgerline.extensions import db
from ledgerline.models import Customer, Price, Subscription


def _resolve_items(raw_items):
    return [
        (get_or_404(Price, item["price"], param="items"), item.get("quantity"))
        for item in raw_items
    ]


@api_bp.route("/subscriptions", methods=["POST"])
def create_subscription():
    data = load(SubscriptionCreateSchema())
    customer = get_or_404(Customer, data["customer"], param="customer")
    subscription = service.create_subscription(
        customer,
        _resolve_items(data["items"]),
        trial_period_days=data.get("trial_period_days"),
        collection_method=data["collection_method"],
        days_until_due=data.get("days_until_due"),
    )
    db.session.commit()
    return jsonify(serialize_subscription(subscription)), 201


@api_bp.route("/subscriptions", methods=["GET"])
def list_subscriptions():
    query = scoped(Subscription)
    if request.args.get("customer"):
        customer = get_or_404(Customer, request.args["customer"], param="customer")
        query = query.filter(Subscription.customer_id == customer.id)
    if request.args.get("status"):
        query = query.filter(Subscription.status == request.args["status"])
    return jsonify(paginate(query, Subscription, serialize_subscription))


@api_bp.route("/subscriptions/<subscription_id>", methods=["GET"])
def get_subscription(subscription_id):
    return jsonify(serialize_subscription(get_or_404(Subscription, subscription_id)))


@api_bp.route("/subscriptions/<subscription_id>", methods=["POST"])
def update_subscription(subscription_id):
    subscription = get_or_404(Subscription, subscription_id)
    data = load(SubscriptionUpdateSchema())
    if "items" in data:
        service.update_subscription_items(
            subscription,
            _resolve_items(data["items"]),
            proration_behavior=data["proration_behavior"],
        )
    if "cancel_at_period_end" in data:
        service.schedule_cancellation(subscription, data["cancel_at_period_end"])
    db.session.commit()
    return jsonify(serialize_subscription(subscription))


@api_bp.route("/subscriptions/<subscription_id>/cancel", methods=["POST"])
def cancel_subscription(subscription_id):
    subscription = get_or_404(Subscription, subscription_id)
    data = load(SubscriptionCancelSchema())
    service.cancel_subscription(
        subscription, prorate=data["prorate"], invoice_now=data["invoice_now"]
    )
    db.session.commit()
    return jsonify(serialize_subscription(subscription))
