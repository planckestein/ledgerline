"""/v1/tax_rates"""
from flask import g, jsonify

from ledgerline.api import api_bp
from ledgerline.api.helpers import get_or_404, load, scoped
from ledgerline.api.idempotency import idempotent
from ledgerline.api.pagination import paginate
from ledgerline.api.schemas import TaxRateSchema, TaxRateUpdateSchema
from ledgerline.extensions import db
from ledgerline.geo import normalize_country
from ledgerline.models import TaxRate
from ledgerline.serializers import serialize_tax_rate


@api_bp.route("/tax_rates", methods=["POST"])
@idempotent
def create_tax_rate():
    data = load(TaxRateSchema())
    rate = TaxRate(
        tenant_id=g.tenant.id,
        display_name=data["display_name"],
        percentage=data["percentage"],
        inclusive=data["inclusive"],
        country=normalize_country(data.get("country")),
        state=(data.get("state") or None),
    )
    db.session.add(rate)
    db.session.commit()
    return jsonify(serialize_tax_rate(rate)), 201


@api_bp.route("/tax_rates", methods=["GET"])
def list_tax_rates():
    return jsonify(paginate(scoped(TaxRate), TaxRate, serialize_tax_rate))


@api_bp.route("/tax_rates/<rate_id>", methods=["GET"])
def get_tax_rate(rate_id):
    return jsonify(serialize_tax_rate(get_or_404(TaxRate, rate_id)))


@api_bp.route("/tax_rates/<rate_id>", methods=["POST"])
@idempotent
def update_tax_rate(rate_id):
    rate = get_or_404(TaxRate, rate_id)
    for key, value in load(TaxRateUpdateSchema()).items():
        setattr(rate, key, value)
    db.session.commit()
    return jsonify(serialize_tax_rate(rate))
