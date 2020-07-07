"""Metered usage: recording and aggregation."""
from sqlalchemy import func

from ledgerline import clock
from ledgerline.errors import InvalidRequestError
from ledgerline.extensions import db
from ledgerline.models import UsageRecord
from ledgerline.models.subscription import BILLABLE_STATUSES

AGGREGATIONS = ("sum", "max", "last_during_period")


def record_usage(item, quantity, timestamp=None):
    """Record ``quantity`` units of usage for a metered subscription item.

    The timestamp must fall within the subscription's current period. Usage
    reported while a subscription is trialing is accepted but never billed.
    """
    subscription = item.subscription
    if item.deleted_at is not None:
        raise InvalidRequestError("Subscription item has been removed", param="subscription_item")
    if not item.price.is_metered:
        raise InvalidRequestError(
            "Usage can only be reported for metered prices", param="subscription_item"
        )
    if subscription.status not in BILLABLE_STATUSES:
        raise InvalidRequestError(
            "Cannot report usage for a %s subscription" % subscription.status,
            param="subscription_item",
        )
    if quantity < 0:
        raise InvalidRequestError("quantity must not be negative", param="quantity")

    moment = timestamp or clock.utcnow()
    if not subscription.current_period_start <= moment < subscription.current_period_end:
        raise InvalidRequestError(
            "timestamp must fall within the current billing period", param="timestamp"
        )

    record = UsageRecord(subscription_item=item, quantity=quantity, timestamp=moment)
    db.session.add(record)
    return record


def aggregate_usage(item, period_start, period_end):
    """Aggregate usage reported in ``[period_start, period_end)`` for ``item``."""
    query = UsageRecord.query.filter(
        UsageRecord.subscription_item_id == item.id,
        UsageRecord.timestamp >= period_start,
        UsageRecord.timestamp <= period_end,
    )
    mode = item.price.aggregate_usage or "sum"
    if mode == "sum":
        return int(query.with_entities(func.coalesce(func.sum(UsageRecord.quantity), 0)).scalar())
    if mode == "max":
        return int(query.with_entities(func.coalesce(func.max(UsageRecord.quantity), 0)).scalar())
    if mode == "last_during_period":
        record = query.order_by(UsageRecord.timestamp.desc(), UsageRecord.id.desc()).first()
        return record.quantity if record else 0
    raise ValueError("Unknown aggregate_usage %r" % (mode,))
