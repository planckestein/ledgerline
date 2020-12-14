# 2020 compatibility

Ledgerline is built exclusively with the technology that was available at the
end of 2020: the language version, every library, the container images, the
CI actions and the development workflow. This document shows the evidence and
explains how the constraint is enforced automatically.

The constraint is documented below with release dates that anyone can check
on PyPI and Docker Hub, and enforced by an automated check that runs in CI on
every push.

## Runtime and infrastructure

| component | version | released |
|---|---|---|
| Python (Docker image / CI container) | 3.8.6 (`python:3.8.6-slim-buster`) | 2020-09-24 |
| PostgreSQL | 12.4 (`postgres:12.4`) | 2020-08-13 |
| Redis | 6.0.9 (`redis:6.0.9`) | 2020-10-27 |
| GitHub Actions checkout | `actions/checkout@v2` | 2019-12 |
| docker-compose file format | 3.8 | 2020-04 |

`setup.py` restricts the interpreter to `>=3.8,<3.9`, and the test suite
asserts that it runs on Python 3.8.

## Python dependencies

Every dependency, including transitive ones, is pinned with `==`. Dates are
the first upload of each release to PyPI.

### Runtime (`requirements.txt`)

| package | version | released |
|---|---|---|
| Flask | 1.1.2 | 2020-04-03 |
| Werkzeug | 1.0.1 | 2020-03-31 |
| Jinja2 | 2.11.2 | 2020-04-13 |
| MarkupSafe | 1.1.1 | 2019-02-24 |
| itsdangerous | 1.1.0 | 2018-10-27 |
| click | 7.1.2 | 2020-04-27 |
| SQLAlchemy | 1.3.20 | 2020-10-12 |
| Flask-SQLAlchemy | 2.4.4 | 2020-07-14 |
| Alembic | 1.4.3 | 2020-09-11 |
| Flask-Migrate | 2.5.3 | 2020-03-14 |
| Mako | 1.1.3 | 2020-05-29 |
| python-editor | 1.0.4 | 2019-02-01 |
| python-dateutil | 2.8.1 | 2019-11-03 |
| marshmallow | 3.8.0 | 2020-09-16 |
| psycopg2-binary | 2.8.6 | 2020-09-06 |
| Celery | 4.4.7 | 2020-07-31 |
| kombu | 4.6.11 | 2020-06-24 |
| billiard | 3.6.3.0 | 2020-02-27 |
| amqp | 2.6.1 | 2020-07-31 |
| vine | 1.3.0 | 2019-03-19 |
| redis (client) | 3.5.3 | 2020-06-01 |
| pytz | 2020.1 | 2020-04-28 |
| requests | 2.24.0 | 2020-06-17 |
| urllib3 | 1.25.11 | 2020-10-19 |
| certifi | 2020.6.20 | 2020-06-20 |
| chardet | 3.0.4 | 2017-06-08 |
| idna | 2.10 | 2020-06-27 |
| six | 1.15.0 | 2020-05-21 |
| gunicorn | 20.0.4 | 2019-11-26 |

### Development (`requirements-dev.txt`)

| package | version | released |
|---|---|---|
| pytest | 6.1.1 | 2020-10-03 |
| pytest-cov | 2.10.1 | 2020-08-14 |
| coverage | 5.3 | 2020-09-13 |
| black | 20.8b1 | 2020-08-26 |
| flake8 | 3.8.4 | 2020-10-02 |
| pycodestyle | 2.6.0 | 2020-05-11 |
| pyflakes | 2.2.0 | 2020-04-10 |
| mccabe | 0.6.1 | 2017-01-26 |
| isort | 5.6.4 | 2020-10-13 |
| attrs | 20.2.0 | 2020-09-05 |
| iniconfig | 1.1.1 | 2020-10-14 |
| packaging | 20.4 | 2020-05-19 |
| pluggy | 0.13.1 | 2019-11-21 |
| py | 1.9.0 | 2020-06-25 |
| pyparsing | 2.4.7 | 2020-04-05 |
| toml | 0.10.1 | 2020-05-14 |
| regex | 2020.10.23 | 2020-10-23 |
| typed-ast | 1.4.1 | 2020-01-13 |
| typing-extensions | 3.7.4.3 | 2020-08-23 |
| mypy-extensions | 0.4.3 | 2019-10-17 |
| pathspec | 0.8.0 | 2020-04-09 |
| appdirs | 1.4.4 | 2020-05-11 |
| colorama (Windows only) | 0.4.4 | 2020-10-13 |
| atomicwrites (Windows only) | 1.4.0 | 2020-04 ¹ |

¹ The 1.4.0 files of `atomicwrites` were re-uploaded to PyPI after the
release, so PyPI shows a later upload date than the April 2020 release. It is
installed on Windows only (pytest dependency) and never on Linux/CI. This is
the single documented exception in `scripts/check_2020_compat.py`.

## Code written against 2020 APIs

The code deliberately uses the idioms of these versions rather than later ones:

* **Python 3.8** only: `typing.List`/`Dict` instead of `list[int]`, no `dict |
  dict`, no `str.removeprefix`, no `zoneinfo`, no `match` statements.
* **Flask 1.1**: `@bp.route(..., methods=["POST"])` (the `@bp.post` shortcuts
  arrived in Flask 2.0), application factory with blueprints,
  `app.test_cli_runner()`.
* **SQLAlchemy 1.3**: the legacy `Model.query` / `Query` API,
  `select([columns])` with a list, `connection.execute(text(...), key=value)`
  with keyword bind parameters (removed in 2.0),
  `declared_attr` mixins; no 1.4/2.0 `future=True` or typed `Mapped[]`.
* **Flask-SQLAlchemy 2.4 / Flask-Migrate 2.5**: `render_as_batch` through
  `configure_args`, the 2.5 `env.py` template.
* **marshmallow 3.8**: `missing=` defaults (`load_default` came in 3.13).
* **Celery 4.4**: the `ContextTask` pattern for Flask application contexts,
  `task_always_eager` in tests.
* **Alembic 1.4**: batch migrations with explicit constraint names for SQLite.

## Development workflow of the time

* Dependencies pinned with `==` in `requirements*.txt` (pip-tools style, with
  `requirements.in` as the source).
* Formatting and linting with black 20.8b1, isort 5 and flake8 3.8, configured
  in `pyproject.toml` / `setup.cfg`, wrapped in a `Makefile`.
* CI on GitHub Actions with `actions/checkout@v2`, Python 3.8.6 and
  PostgreSQL 12.4 service containers.
* Local stack with docker-compose (PostgreSQL 12, Redis 6, gunicorn, Celery).

## Enforcement

`scripts/check_2020_compat.py` (standard library only) fails when:

* a requirement is not pinned with `==`;
* `setup.py` allows a Python other than 3.8;
* a Dockerfile, docker-compose or CI image is not one of the pinned 2020
  images, or a GitHub Action newer than `@v2` is used;
* `docker-compose.yml` uses service `profiles` (not supported by docker-compose 1.27);
* a Python file is not valid Python 3.8 syntax or uses an API from the list
  above that did not exist in the pinned versions;
* with `--pypi`: a pinned release was first published after 2020-12-31.

It runs in three places:

```bash
python scripts/check_2020_compat.py --pypi   # by hand
python -m pytest tests/unit/test_toolchain.py
# and as the "compat-2020" job in .github/workflows/ci.yml on every push
```
