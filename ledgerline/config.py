"""Application configuration.

Configuration is selected with the ``LEDGERLINE_CONFIG`` environment variable
(``development``, ``testing`` or ``production``). Every value can be overridden
by passing keyword arguments to :func:`ledgerline.app.create_app`.
"""
import os


class BaseConfig:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-not-secret")

    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", "sqlite:///" + os.path.join(os.getcwd(), "ledgerline-dev.db")
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    JSON_SORT_KEYS = False


class DevelopmentConfig(BaseConfig):
    DEBUG = True


class TestingConfig(BaseConfig):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = os.environ.get("TEST_DATABASE_URL", "sqlite://")


class ProductionConfig(BaseConfig):
    SECRET_KEY = os.environ.get("SECRET_KEY")


CONFIGS = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}


def get_config(name=None):
    name = name or os.environ.get("LEDGERLINE_CONFIG", "development")
    try:
        return CONFIGS[name]
    except KeyError:
        raise RuntimeError(
            "Unknown configuration %r (expected one of %s)" % (name, sorted(CONFIGS))
        )
