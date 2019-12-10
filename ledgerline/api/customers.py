"""/v1/customers"""
from flask import g, jsonify, request

from ledgerline.api import api_bp
from ledgerline.api.helpers import get_or_404, load, scoped
from ledgerline.api.pagination import paginate
from ledgerline.api.schemas import CustomerSchema
from ledgerline.api.serializers import serialize_customer
from ledgerline.extensions import db
from ledgerline.geo import serialize_address
from ledgerline.models import Customer


def _apply_fields(customer, data):
    if "email" in data:
        customer.email = data["email"]
    if "name" in data:
        customer.name = data["name"]
    if "address" in data:
        customer.billing_address = serialize_address(data["address"])
    if "metadata" in data:
        customer.metadata_ = data["metadata"]


@api_bp.route("/customers", methods=["POST"])
def create_customer():
    data = load(CustomerSchema())
    customer = Customer(tenant_id=g.tenant.id)
    _apply_fields(customer, data)
    db.session.add(customer)
    db.session.commit()
    return jsonify(serialize_customer(customer)), 201


@api_bp.route("/customers", methods=["GET"])
def list_customers():
    query = scoped(Customer)
    if request.args.get("email"):
        query = query.filter(Customer.email == request.args["email"])
    return jsonify(paginate(query, Customer, serialize_customer))


@api_bp.route("/customers/<customer_id>", methods=["GET"])
def get_customer(customer_id):
    return jsonify(serialize_customer(get_or_404(Customer, customer_id)))


@api_bp.route("/customers/<customer_id>", methods=["POST"])
def update_customer(customer_id):
    customer = get_or_404(Customer, customer_id)
    data = load(CustomerSchema(partial=True))
    _apply_fields(customer, data)
    db.session.commit()
    return jsonify(serialize_customer(customer))
