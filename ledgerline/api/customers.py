"""/v1/customers"""
from flask import g, jsonify, request

from ledgerline.api import api_bp
from ledgerline.api.helpers import get_or_404, load, scoped
from ledgerline.api.idempotency import idempotent
from ledgerline.api.pagination import paginate
from ledgerline.api.schemas import CustomerDiscountSchema, CustomerSchema, PaymentMethodSchema
from ledgerline.billing import discounts
from ledgerline.events import bus
from ledgerline.extensions import db
from ledgerline.geo import serialize_address
from ledgerline.models import Coupon, Customer, PaymentMethod
from ledgerline.payments import service as payment_service
from ledgerline.serializers import serialize_customer, serialize_payment_method


def _apply_fields(customer, data):
    if "email" in data:
        customer.email = data["email"]
    if "name" in data:
        customer.name = data["name"]
    if "address" in data:
        customer.billing_address = serialize_address(data["address"])
    if "vat_id" in data:
        vat_id = (data["vat_id"] or "").strip()
        customer.vat_id = vat_id or None
    if "tax_exempt" in data:
        customer.tax_exempt = data["tax_exempt"]
    if "metadata" in data:
        customer.metadata_ = data["metadata"]


@api_bp.route("/customers", methods=["POST"])
@idempotent
def create_customer():
    data = load(CustomerSchema())
    customer = Customer(tenant_id=g.tenant.id, tax_exempt=False)
    _apply_fields(customer, data)
    db.session.add(customer)
    bus.publish("customer.created", customer)
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
@idempotent
def update_customer(customer_id):
    customer = get_or_404(Customer, customer_id)
    data = load(CustomerSchema(partial=True))
    _apply_fields(customer, data)
    bus.publish("customer.updated", customer)
    db.session.commit()
    return jsonify(serialize_customer(customer))


@api_bp.route("/customers/<customer_id>/payment_methods", methods=["POST"])
@idempotent
def attach_payment_method(customer_id):
    customer = get_or_404(Customer, customer_id)
    data = load(PaymentMethodSchema())
    method = payment_service.attach_payment_method(
        customer, data["token"], set_default=data["set_default"]
    )
    db.session.commit()
    return jsonify(serialize_payment_method(method)), 201


@api_bp.route("/customers/<customer_id>/payment_methods", methods=["GET"])
def list_payment_methods(customer_id):
    customer = get_or_404(Customer, customer_id)
    query = scoped(PaymentMethod).filter(
        PaymentMethod.customer_id == customer.id, PaymentMethod.detached_at.is_(None)
    )
    return jsonify(paginate(query, PaymentMethod, serialize_payment_method))


@api_bp.route("/customers/<customer_id>/discount", methods=["POST"])
@idempotent
def apply_customer_discount(customer_id):
    customer = get_or_404(Customer, customer_id)
    data = load(CustomerDiscountSchema())
    coupon = get_or_404(Coupon, data["coupon"], param="coupon")
    discount = discounts.create_discount(coupon, customer)
    db.session.commit()
    return (
        jsonify(
            {
                "id": discount.public_id,
                "object": "discount",
                "coupon": coupon.public_id,
                "customer": customer.public_id,
                "subscription": None,
            }
        ),
        201,
    )
