"""/v1/invoices and /v1/invoiceitems"""
from flask import g, jsonify, request

from ledgerline.api import api_bp
from ledgerline.api.helpers import bool_arg, get_or_404, load, scoped
from ledgerline.api.idempotency import idempotent
from ledgerline.api.pagination import paginate
from ledgerline.api.schemas import InvoiceCreateSchema, InvoiceItemSchema, InvoicePaySchema
from ledgerline.billing import invoicing
from ledgerline.errors import CardError, InvalidRequestError
from ledgerline.extensions import db
from ledgerline.models import Customer, Invoice, InvoiceItem, PaymentAttempt, Subscription
from ledgerline.serializers import (
    serialize_invoice,
    serialize_invoice_item,
    serialize_payment_attempt,
)


@api_bp.route("/invoiceitems", methods=["POST"])
@idempotent
def create_invoice_item():
    data = load(InvoiceItemSchema())
    customer = get_or_404(Customer, data["customer"], param="customer")
    subscription = None
    if data.get("subscription"):
        subscription = get_or_404(Subscription, data["subscription"], param="subscription")
        if subscription.customer_id != customer.id:
            raise InvalidRequestError(
                "Subscription does not belong to this customer", param="subscription"
            )
    if customer.currency is None:
        customer.currency = data["currency"]
    elif customer.currency != data["currency"]:
        raise InvalidRequestError(
            "Customer %s is billed in %s" % (customer.public_id, customer.currency),
            param="currency",
        )
    item = InvoiceItem(
        tenant_id=g.tenant.id,
        customer=customer,
        subscription=subscription,
        amount=data["amount"],
        currency=data["currency"],
        description=data["description"],
    )
    db.session.add(item)
    db.session.commit()
    return jsonify(serialize_invoice_item(item)), 201


@api_bp.route("/invoiceitems", methods=["GET"])
def list_invoice_items():
    query = scoped(InvoiceItem)
    if request.args.get("customer"):
        customer = get_or_404(Customer, request.args["customer"], param="customer")
        query = query.filter(InvoiceItem.customer_id == customer.id)
    pending = bool_arg("pending")
    if pending is True:
        query = query.filter(InvoiceItem.invoice_id.is_(None))
    return jsonify(paginate(query, InvoiceItem, serialize_invoice_item))


@api_bp.route("/invoices", methods=["POST"])
@idempotent
def create_invoice():
    data = load(InvoiceCreateSchema())
    customer = get_or_404(Customer, data["customer"], param="customer")
    invoice = invoicing.create_manual_invoice(
        customer,
        collection_method=data["collection_method"],
        days_until_due=data.get("days_until_due"),
    )
    db.session.commit()
    return jsonify(serialize_invoice(invoice)), 201


@api_bp.route("/invoices", methods=["GET"])
def list_invoices():
    query = scoped(Invoice)
    if request.args.get("customer"):
        customer = get_or_404(Customer, request.args["customer"], param="customer")
        query = query.filter(Invoice.customer_id == customer.id)
    if request.args.get("subscription"):
        subscription = get_or_404(Subscription, request.args["subscription"], param="subscription")
        query = query.filter(Invoice.subscription_id == subscription.id)
    if request.args.get("status"):
        query = query.filter(Invoice.status == request.args["status"])
    return jsonify(paginate(query, Invoice, serialize_invoice))


@api_bp.route("/invoices/<invoice_id>", methods=["GET"])
def get_invoice(invoice_id):
    return jsonify(serialize_invoice(get_or_404(Invoice, invoice_id)))


@api_bp.route("/invoices/<invoice_id>/finalize", methods=["POST"])
@idempotent
def finalize_invoice(invoice_id):
    invoice = get_or_404(Invoice, invoice_id)
    invoicing.finalize_invoice(invoice)
    db.session.commit()
    return jsonify(serialize_invoice(invoice))


@api_bp.route("/invoices/<invoice_id>/pay", methods=["POST"])
@idempotent
def pay_invoice(invoice_id):
    invoice = get_or_404(Invoice, invoice_id)
    data = load(InvoicePaySchema())
    result = invoicing.pay_invoice(invoice, paid_out_of_band=data["paid_out_of_band"])
    db.session.commit()
    if isinstance(result, PaymentAttempt) and result.status == "failed":
        raise CardError(result.failure_message or "Payment failed", code=result.failure_code)
    return jsonify(serialize_invoice(invoice))


@api_bp.route("/invoices/<invoice_id>/void", methods=["POST"])
@idempotent
def void_invoice(invoice_id):
    invoice = get_or_404(Invoice, invoice_id)
    invoicing.void_invoice(invoice)
    db.session.commit()
    return jsonify(serialize_invoice(invoice))


@api_bp.route("/invoices/<invoice_id>/mark_uncollectible", methods=["POST"])
@idempotent
def mark_uncollectible(invoice_id):
    invoice = get_or_404(Invoice, invoice_id)
    invoicing.mark_uncollectible(invoice)
    db.session.commit()
    return jsonify(serialize_invoice(invoice))


@api_bp.route("/invoices/<invoice_id>/payment_attempts", methods=["GET"])
def list_payment_attempts(invoice_id):
    invoice = get_or_404(Invoice, invoice_id)
    return jsonify(
        {
            "object": "list",
            "url": request.path,
            "has_more": False,
            "data": [serialize_payment_attempt(a) for a in invoice.payment_attempts],
        }
    )
