"""/v1/subscription_items/<id>/usage_records"""
from flask import jsonify

from ledgerline.api import api_bp
from ledgerline.api.helpers import from_timestamp, get_or_404, load
from ledgerline.api.schemas import UsageRecordSchema
from ledgerline.billing import usage
from ledgerline.extensions import db
from ledgerline.models import SubscriptionItem
from ledgerline.serializers import serialize_usage_record


@api_bp.route("/subscription_items/<item_id>/usage_records", methods=["POST"])
def create_usage_record(item_id):
    item = get_or_404(SubscriptionItem, item_id, param="subscription_item")
    data = load(UsageRecordSchema())
    record = usage.record_usage(
        item, data["quantity"], timestamp=from_timestamp(data.get("timestamp"), "timestamp")
    )
    db.session.commit()
    return jsonify(serialize_usage_record(record)), 201


@api_bp.route("/subscription_items/<item_id>/usage_summary", methods=["GET"])
def usage_summary(item_id):
    item = get_or_404(SubscriptionItem, item_id, param="subscription_item")
    subscription = item.subscription
    total = usage.aggregate_usage(
        item, subscription.current_period_start, subscription.current_period_end
    )
    return jsonify(
        {
            "object": "usage_summary",
            "subscription_item": item.public_id,
            "aggregate_usage": item.price.aggregate_usage,
            "total_usage": total,
        }
    )
