import re

from setuptools import find_packages, setup

with open("ledgerline/__init__.py", encoding="utf-8") as handle:
    VERSION = re.search(r'__version__ = "([^"]+)"', handle.read()).group(1)

setup(
    name="ledgerline",
    version=VERSION,
    description="Multi-tenant subscription billing service",
    packages=find_packages(exclude=["tests", "tests.*", "tasks", "tasks.*"]),
    python_requires=">=3.8,<3.9",
    install_requires=[
        "alembic~=1.4",
        "celery[redis]~=4.4",
        "flask~=1.1",
        "flask-migrate~=2.5",
        "flask-sqlalchemy~=2.4",
        "marshmallow~=3.6",
        "psycopg2-binary~=2.8",
        "requests~=2.23",
        "sqlalchemy~=1.3",
    ],
)
