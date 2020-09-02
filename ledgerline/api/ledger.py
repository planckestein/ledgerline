"""/v1/ledger"""
from flask import g, jsonify, request

from ledgerline.api import api_bp
from ledgerline.currency import UnknownCurrencyError, normalize_currency
from ledgerline.errors import InvalidRequestError
from ledgerline.ledger import reports


@api_bp.route("/ledger/trial_balance", methods=["GET"])
def trial_balance():
    try:
        currency = normalize_currency(request.args.get("currency") or g.tenant.default_currency)
    except UnknownCurrencyError:
        raise InvalidRequestError("Unsupported currency", param="currency")
    body = reports.trial_balance(g.tenant.id, currency)
    body["object"] = "trial_balance"
    return jsonify(body)
