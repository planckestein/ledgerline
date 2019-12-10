"""Small helpers shared by the resource modules."""
import datetime

from flask import g, request
from marshmallow import ValidationError

from ledgerline.errors import InvalidRequestError, NotFoundError


def request_json():
    if not request.get_data():
        return {}
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise InvalidRequestError("Request body must be a JSON object")
    return data


def _first_error(messages, prefix=""):
    """Return ``(param, message)`` for the first error in a marshmallow error dict."""
    for key in sorted(messages, key=str):
        value = messages[key]
        param = "%s%s" % (prefix, key)
        if isinstance(value, dict):
            return _first_error(value, param + ".")
        if isinstance(value, list) and value:
            if isinstance(value[0], dict):
                return _first_error(value[0], param + ".")
            return param, str(value[0])
        return param, str(value)
    return None, "Invalid request"


def load(schema, data=None):
    try:
        return schema.load(request_json() if data is None else data)
    except ValidationError as exc:
        messages = exc.messages if isinstance(exc.messages, dict) else {"_schema": exc.messages}
        param, message = _first_error(messages)
        if param == "_schema":
            param = None
        raise InvalidRequestError(message, param=param)


def scoped(model):
    """Query ``model`` restricted to the authenticated tenant."""
    return model.query.filter(model.tenant_id == g.tenant.id)


def get_or_404(model, public_id, param=None):
    obj = scoped(model).filter(model.public_id == public_id).first()
    if obj is None:
        raise NotFoundError(
            "No such %s: '%s'" % (model.__name__.lower(), public_id), param=param or "id"
        )
    return obj


def from_timestamp(value, param):
    if value is None:
        return None
    try:
        return datetime.datetime.utcfromtimestamp(int(value))
    except (TypeError, ValueError, OverflowError):
        raise InvalidRequestError("Invalid timestamp", param=param)


def bool_arg(name):
    value = request.args.get(name)
    if value is None:
        return None
    return value.lower() in ("1", "true", "yes")
