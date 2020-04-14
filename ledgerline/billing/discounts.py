"""Coupons and discounts.

A coupon is redeemed into a :class:`~ledgerline.models.Discount` attached to a
customer or a subscription. When an invoice is built, at most one discount
applies: a subscription discount wins over a customer discount.

Discounts only reduce lines with a positive amount; credits (e.g. proration
credits) are never discounted.
"""
from datetime import timedelta

from sqlalchemy import or_

from ledgerline import clock
from ledgerline.billing.periods import add_months
from ledgerline.errors import InvalidRequestError
from ledgerline.extensions import db
from ledgerline.models import Discount
from ledgerline.money import Money


def assert_redeemable(coupon, currency=None):
    if not coupon.valid:
        raise InvalidRequestError("Coupon %s is no longer valid" % coupon.public_id, param="coupon")
    if coupon.max_redemptions is not None and coupon.times_redeemed >= coupon.max_redemptions:
        raise InvalidRequestError(
            "Coupon %s has reached its maximum number of redemptions" % coupon.public_id,
            param="coupon",
        )
    if coupon.amount_off is not None and currency and coupon.currency != currency:
        raise InvalidRequestError(
            "Coupon %s is in %s but the subscription is billed in %s"
            % (coupon.public_id, coupon.currency, currency),
            param="coupon",
        )


def create_discount(coupon, customer, subscription=None, start=None, currency=None):
    """Redeem ``coupon`` for ``customer`` (optionally scoped to one subscription)."""
    assert_redeemable(coupon, currency or customer.currency)
    start = start or clock.utcnow()
    end = None
    if coupon.duration == "repeating":
        end = add_months(start, coupon.duration_in_months)
    discount = Discount(
        tenant_id=customer.tenant_id,
        coupon=coupon,
        customer=customer,
        subscription=subscription,
        start=start,
        end=end,
    )
    coupon.times_redeemed += 1
    if coupon.max_redemptions is not None and coupon.times_redeemed >= coupon.max_redemptions:
        coupon.valid = False
    db.session.add(discount)
    return discount


def active_discount_for(invoice):
    """Return the discount that applies to ``invoice``, or ``None``.

    The reference time is the start of the invoiced period, so a ``repeating``
    coupon for 3 months covers exactly three monthly invoices.
    """
    reference = invoice.period_start or clock.utcnow()
    query = Discount.query.filter(
        Discount.customer_id == invoice.customer_id,
        Discount.start <= reference,
        or_(Discount.end.is_(None), Discount.end > reference),
    )
    candidates = query.order_by(Discount.id).all()
    subscription_discounts = [
        d
        for d in candidates
        if invoice.subscription_id is not None and d.subscription_id == invoice.subscription_id
    ]
    if subscription_discounts:
        return subscription_discounts[0]
    customer_discounts = [d for d in candidates if d.subscription_id is None]
    return customer_discounts[0] if customer_discounts else None


def apply_discount(lines, coupon, currency):
    """Set ``discount_amount`` on every line and return the invoice discount total."""
    for line in lines:
        line.discount_amount = 0
    if coupon is None:
        return 0
    discountable = [line for line in lines if line.amount > 0]
    if not discountable:
        return 0
    discountable_total = sum(line.amount for line in discountable)

    if coupon.amount_off is not None:
        if coupon.currency != currency:
            return 0
        total = Money(min(coupon.amount_off, discountable_total), currency)
        shares = total.allocate([line.amount for line in discountable])
        for line, share in zip(discountable, shares):
            line.discount_amount = share.amount
        return total.amount

    percent = coupon.percent_off
    for line in discountable:
        line.discount_amount = Money(line.amount, currency).percentage(percent).amount
    return Money(discountable_total, currency).percentage(percent).amount


def close_once_discount(discount, at):
    """``once`` coupons stop applying after the first invoice that used them."""
    if discount is not None and discount.coupon.duration == "once" and discount.end is None:
        # End strictly after the invoice's reference time so it is not re-evaluated
        # as inactive for the invoice that is being finalized right now.
        discount.end = at + timedelta(microseconds=1)
