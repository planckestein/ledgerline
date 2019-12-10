"""Request validation schemas (marshmallow 3).

Unknown fields are rejected so that typos in parameter names surface as
``400 invalid_request_error`` with ``param`` set to the offending field.
"""
from marshmallow import Schema, fields, validate


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
