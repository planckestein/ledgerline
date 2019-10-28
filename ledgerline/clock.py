"""Injectable wall clock.

All domain code reads the current time through :func:`utcnow` so that tests
(and the ``billing simulate`` CLI) can freeze or advance time deterministically.
Datetimes are naive and always expressed in UTC.
"""
import datetime


class SystemClock:
    def now(self):
        return datetime.datetime.utcnow()


class FrozenClock:
    """A clock that only moves when told to."""

    def __init__(self, at):
        self._now = at

    def now(self):
        return self._now

    def set(self, at):
        self._now = at

    def advance(self, **delta):
        self._now = self._now + datetime.timedelta(**delta)
        return self._now


_clock = SystemClock()


def utcnow():
    return _clock.now()


def get_clock():
    return _clock


def set_clock(clock):
    """Install ``clock`` and return the previously installed clock."""
    global _clock
    previous, _clock = _clock, clock
    return previous
