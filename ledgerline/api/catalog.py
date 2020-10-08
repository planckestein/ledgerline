"""/v1/products and /v1/prices"""
from flask import g, jsonify, request

from ledgerline.api import api_bp
from ledgerline.api.helpers import bool_arg, get_or_404, load, scoped
from ledgerline.api.idempotency import idempotent
from ledgerline.api.pagination import paginate
from ledgerline.api.schemas import (
    PriceSchema,
    PriceUpdateSchema,
    ProductSchema,
    ProductUpdateSchema,
)
from ledgerline.extensions import db
from ledgerline.models import Price, Product
from ledgerline.serializers import serialize_price, serialize_product


@api_bp.route("/products", methods=["POST"])
@idempotent
def create_product():
    data = load(ProductSchema())
    product = Product(tenant_id=g.tenant.id, **data)
    db.session.add(product)
    db.session.commit()
    return jsonify(serialize_product(product)), 201


@api_bp.route("/products", methods=["GET"])
def list_products():
    query = scoped(Product)
    active = bool_arg("active")
    if active is not None:
        query = query.filter(Product.active == active)
    return jsonify(paginate(query, Product, serialize_product))


@api_bp.route("/products/<product_id>", methods=["GET"])
def get_product(product_id):
    return jsonify(serialize_product(get_or_404(Product, product_id)))


@api_bp.route("/products/<product_id>", methods=["POST"])
@idempotent
def update_product(product_id):
    product = get_or_404(Product, product_id)
    for key, value in load(ProductUpdateSchema()).items():
        setattr(product, key, value)
    db.session.commit()
    return jsonify(serialize_product(product))


@api_bp.route("/prices", methods=["POST"])
@idempotent
def create_price():
    data = load(PriceSchema())
    product = get_or_404(Product, data["product"], param="product")
    recurring = data["recurring"]
    usage_type = recurring.get("usage_type", "licensed")
    price = Price(
        tenant_id=g.tenant.id,
        product=product,
        nickname=data.get("nickname"),
        currency=data["currency"],
        unit_amount=data["unit_amount"],
        billing_scheme=data["billing_scheme"],
        package_size=data.get("package_size"),
        interval=recurring["interval"],
        interval_count=recurring.get("interval_count", 1),
        usage_type=usage_type,
        aggregate_usage=(recurring.get("aggregate_usage") or "sum")
        if usage_type == "metered"
        else None,
    )
    db.session.add(price)
    db.session.commit()
    return jsonify(serialize_price(price)), 201


@api_bp.route("/prices", methods=["GET"])
def list_prices():
    query = scoped(Price)
    if request.args.get("product"):
        product = get_or_404(Product, request.args["product"], param="product")
        query = query.filter(Price.product_id == product.id)
    active = bool_arg("active")
    if active is not None:
        query = query.filter(Price.active == active)
    return jsonify(paginate(query, Price, serialize_price))


@api_bp.route("/prices/<price_id>", methods=["GET"])
def get_price(price_id):
    return jsonify(serialize_price(get_or_404(Price, price_id)))


@api_bp.route("/prices/<price_id>", methods=["POST"])
@idempotent
def update_price(price_id):
    price = get_or_404(Price, price_id)
    for key, value in load(PriceUpdateSchema()).items():
        setattr(price, key, value)
    db.session.commit()
    return jsonify(serialize_price(price))
