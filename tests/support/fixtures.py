"""Pytest fixtures shared by every test suite."""
import datetime

import pytest

from ledgerline.app import create_app
from ledgerline.clock import FrozenClock, set_clock
from ledgerline.extensions import db as _db

# Every test starts at the same, boring instant unless it moves the clock.
START = datetime.datetime(2020, 6, 1, 12, 0, 0)


@pytest.fixture(autouse=True)
def clock():
    frozen = FrozenClock(START)
    previous = set_clock(frozen)
    yield frozen
    set_clock(previous)


@pytest.fixture
def app():
    app = create_app("testing")
    with app.app_context():
        _db.create_all()
        yield app
        _db.session.remove()
        _db.drop_all()


@pytest.fixture
def db(app):
    return _db
