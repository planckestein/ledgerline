"""Shared model building blocks."""
import json
import secrets
import string

from sqlalchemy.ext.declarative import declared_attr
from sqlalchemy.types import Text, TypeDecorator

from ledgerline import clock
from ledgerline.extensions import db

_ALPHABET = string.ascii_letters + string.digits


def generate_public_id(prefix, length=24):
    """Return an opaque, URL-safe identifier such as ``cus_Xb81...``."""
    return "%s_%s" % (prefix, "".join(secrets.choice(_ALPHABET) for _ in range(length)))


def utcnow():
    return clock.utcnow()


class JSONText(TypeDecorator):
    """JSON stored in a TEXT column (portable between SQLite and PostgreSQL)."""

    impl = Text

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return json.dumps(value, sort_keys=True, separators=(",", ":"))

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return json.loads(value)


class TimestampMixin:
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)


class PublicIdMixin:
    """Adds an externally visible ``public_id`` with a type prefix.

    Integer primary keys never leave the service; the API only exposes public ids.
    """

    __public_id_prefix__ = None

    @declared_attr
    def public_id(cls):
        prefix = cls.__public_id_prefix__
        if not prefix:
            raise TypeError("%s must define __public_id_prefix__" % cls.__name__)
        return db.Column(
            db.String(40),
            nullable=False,
            unique=True,
            default=lambda: generate_public_id(prefix),
        )
