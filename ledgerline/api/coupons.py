"""/v1/coupons"""
from flask import g, jsonify

from ledgerline.api import api_bp
from ledgerline.api.helpers import get_or_404, load, scoped
from ledgerline.api.idempotency import idempotent
from ledgerline.api.pagination import paginate
from ledgerline.api.schemas import CouponSchema
from ledgerline.extensions import db
from ledgerline.models import Coupon
from ledgerline.serializers import serialize_coupon


@api_bp.route("/coupons", methods=["POST"])
@idempotent
def create_coupon():
    data = load(CouponSchema())
    coupon = Coupon(tenant_id=g.tenant.id, times_redeemed=0, valid=True, **data)
    db.session.add(coupon)
    db.session.commit()
    return jsonify(serialize_coupon(coupon)), 201


@api_bp.route("/coupons", methods=["GET"])
def list_coupons():
    return jsonify(paginate(scoped(Coupon), Coupon, serialize_coupon))


@api_bp.route("/coupons/<coupon_id>", methods=["GET"])
def get_coupon(coupon_id):
    return jsonify(serialize_coupon(get_or_404(Coupon, coupon_id)))
