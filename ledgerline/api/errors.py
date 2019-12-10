"""Uniform JSON error responses."""
import logging

from flask import jsonify
from werkzeug.exceptions import HTTPException

from ledgerline.errors import LedgerlineError
from ledgerline.extensions import db

log = logging.getLogger(__name__)


def error_response(exc):
    response = jsonify(exc.to_dict())
    response.status_code = exc.status_code
    return response


def _http_error(exc):
    response = jsonify(
        {
            "error": {
                "type": "invalid_request_error",
                "message": exc.description,
                "code": exc.name.lower().replace(" ", "_"),
            }
        }
    )
    response.status_code = exc.code
    return response


def register_error_handlers(app):
    @app.errorhandler(LedgerlineError)
    def _handle_ledgerline_error(exc):
        db.session.rollback()
        if exc.status_code >= 500:
            log.error("Internal invariant violated: %s", exc.message)
        return error_response(exc)

    @app.errorhandler(HTTPException)
    def _handle_http_error(exc):
        return _http_error(exc)

    @app.errorhandler(Exception)
    def _handle_unexpected(exc):
        if app.config.get("TESTING") and app.config.get("PROPAGATE_EXCEPTIONS", True):
            raise exc
        db.session.rollback()
        log.exception("Unhandled error")
        response = jsonify({"error": {"type": "api_error", "message": "Internal server error"}})
        response.status_code = 500
        return response
