"""Request validation schemas (marshmallow 3).

Unknown fields are rejected so that typos in parameter names surface as
``400 invalid_request_error`` with ``param`` set to the offending field.
"""
from marshmallow import Schema, ValidationError, fields, validate, validates_schema

from ledgerline.billing import periods
from ledgerline.billing.pricing import BILLING_SCHEMES
from ledgerline.billing.subscriptions import COLLECTION_METHODS, PRORATION_BEHAVIORS
from ledgerline.currency import CURRENCY_EXPONENTS


def Currency(**kwargs):  # noqa: N802 - reads like a field class
    return fields.Str(
        validate=validate.OneOf(sorted(CURRENCY_EXPONENTS), error="Unsupported currency"), **kwargs
    )


class AddressSchema(Schema):
    line1 = fields.Str(allow_none=True, validate=validate.Length(max=200))
    line2 = fields.Str(allow_none=True, validate=validate.Length(max=200))
    city = fields.Str(allow_none=True, validate=validate.Length(max=100))
    state = fields.Str(allow_none=True, validate=validate.Length(max=100))
    postal_code = fields.Str(allow_none=True, validate=validate.Length(max=20))
    country = fields.Str(allow_none=True, validate=validate.Length(equal=2))


class CustomerSchema(Schema):
    email = fields.Email(allow_none=True)
    name = fields.Str(allow_none=True, validate=validate.Length(max=200))
    address = fields.Nested(AddressSchema, allow_none=True)
    metadata = fields.Dict(keys=fields.Str(), values=fields.Str())


class PaymentMethodSchema(Schema):
    token = fields.Str(required=True)
    set_default = fields.Bool(missing=True)


class ProductSchema(Schema):
    name = fields.Str(required=True, validate=validate.Length(min=1, max=200))
    description = fields.Str(allow_none=True)
    active = fields.Bool(missing=True)


class ProductUpdateSchema(Schema):
    name = fields.Str(validate=validate.Length(min=1, max=200))
    description = fields.Str(allow_none=True)
    active = fields.Bool()


class RecurringSchema(Schema):
    interval = fields.Str(required=True, validate=validate.OneOf(periods.INTERVALS))
    interval_count = fields.Int(missing=1)

    @validates_schema
    def _check(self, data, **kwargs):
        try:
            periods.validate_interval(data["interval"], data.get("interval_count", 1))
        except ValueError as exc:
            raise ValidationError(str(exc), field_name="interval_count")


class PriceSchema(Schema):
    product = fields.Str(required=True)
    currency = Currency(required=True)
    unit_amount = fields.Int(required=True, validate=validate.Range(min=0))
    billing_scheme = fields.Str(missing="per_unit", validate=validate.OneOf(BILLING_SCHEMES))
    package_size = fields.Int(allow_none=True, validate=validate.Range(min=1))
    nickname = fields.Str(allow_none=True, validate=validate.Length(max=200))
    recurring = fields.Nested(RecurringSchema, required=True)

    @validates_schema
    def _check(self, data, **kwargs):
        scheme = data.get("billing_scheme", "per_unit")
        if scheme == "package" and not data.get("package_size"):
            raise ValidationError("package_size is required for package pricing", "package_size")
        if scheme != "package" and data.get("package_size"):
            raise ValidationError("package_size requires billing_scheme=package", "package_size")


class PriceUpdateSchema(Schema):
    nickname = fields.Str(allow_none=True, validate=validate.Length(max=200))
    active = fields.Bool()


class SubscriptionItemSchema(Schema):
    price = fields.Str(required=True)
    quantity = fields.Int(missing=1, allow_none=True, validate=validate.Range(min=0))


class SubscriptionCreateSchema(Schema):
    customer = fields.Str(required=True)
    items = fields.List(
        fields.Nested(SubscriptionItemSchema),
        required=True,
        validate=validate.Length(min=1, max=20),
    )
    trial_period_days = fields.Int(validate=validate.Range(min=1, max=730))
    collection_method = fields.Str(
        missing="charge_automatically", validate=validate.OneOf(COLLECTION_METHODS)
    )
    days_until_due = fields.Int(validate=validate.Range(min=0, max=365))


class SubscriptionUpdateSchema(Schema):
    items = fields.List(
        fields.Nested(SubscriptionItemSchema), validate=validate.Length(min=1, max=20)
    )
    proration_behavior = fields.Str(
        missing="create_prorations", validate=validate.OneOf(PRORATION_BEHAVIORS)
    )
    cancel_at_period_end = fields.Bool()


class SubscriptionCancelSchema(Schema):
    prorate = fields.Bool(missing=False)
    invoice_now = fields.Bool(missing=False)


class InvoiceItemSchema(Schema):
    customer = fields.Str(required=True)
    subscription = fields.Str()
    amount = fields.Int(required=True)
    currency = Currency(required=True)
    description = fields.Str(required=True, validate=validate.Length(min=1, max=500))

    @validates_schema
    def _check(self, data, **kwargs):
        if data.get("amount") == 0:
            raise ValidationError("amount must not be zero", "amount")


class InvoiceCreateSchema(Schema):
    customer = fields.Str(required=True)
    collection_method = fields.Str(
        missing="charge_automatically", validate=validate.OneOf(COLLECTION_METHODS)
    )
    days_until_due = fields.Int(validate=validate.Range(min=0, max=365))


class InvoicePaySchema(Schema):
    paid_out_of_band = fields.Bool(missing=False)
