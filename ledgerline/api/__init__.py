"""Public REST API (``/v1``).

Resource modules register their routes on :data:`api_bp` when imported.
"""
from flask import Blueprint

api_bp = Blueprint("api", __name__, url_prefix="/v1")


def register_api(app):
    from ledgerline.api import auth, customers, errors  # noqa: F401

    app.register_blueprint(api_bp)
    errors.register_error_handlers(app)
