"""Cursor pagination for list endpoints.

Lists are returned newest first. Clients pass ``limit`` (1-100) and either
``starting_after=<id>`` (next page) or ``ending_before=<id>`` (previous page),
where ``<id>`` is the public id of the last/first object they received::

    {"object": "list", "url": "/v1/customers", "has_more": true, "data": [...]}
"""
from flask import current_app, g, request

from ledgerline.errors import InvalidRequestError


def parse_limit():
    default = current_app.config["LEDGERLINE_PAGE_SIZE_DEFAULT"]
    maximum = current_app.config["LEDGERLINE_PAGE_SIZE_MAX"]
    raw = request.args.get("limit")
    if raw is None:
        return default
    try:
        limit = int(raw)
    except ValueError:
        raise InvalidRequestError("limit must be an integer", param="limit")
    if not 1 <= limit <= maximum:
        raise InvalidRequestError("limit must be between 1 and %d" % maximum, param="limit")
    return limit


def _cursor(model, public_id, param):
    cursor = model.query.filter(
        model.tenant_id == g.tenant.id, model.public_id == public_id
    ).first()
    if cursor is None:
        raise InvalidRequestError("No such object: '%s'" % public_id, param=param)
    return cursor


def paginate(query, model, serializer):
    """Return a list envelope for ``query`` (already filtered by tenant)."""
    limit = parse_limit()
    starting_after = request.args.get("starting_after")
    ending_before = request.args.get("ending_before")
    if starting_after and ending_before:
        raise InvalidRequestError("starting_after and ending_before are mutually exclusive")

    if starting_after:
        cursor = _cursor(model, starting_after, "starting_after")
        rows = (
            query.filter(model.created_at < cursor.created_at)
            .order_by(model.created_at.desc())
            .limit(limit)
            .all()
        )
    elif ending_before:
        cursor = _cursor(model, ending_before, "ending_before")
        rows = (
            query.filter(model.created_at > cursor.created_at)
            .order_by(model.created_at.asc())
            .limit(limit)
            .all()
        )
        rows.reverse()
    else:
        rows = query.order_by(model.created_at.desc()).limit(limit).all()

    return {
        "object": "list",
        "url": request.path,
        "has_more": len(rows) == limit,
        "data": [serializer(row) for row in rows],
    }
