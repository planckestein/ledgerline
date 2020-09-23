from datetime import timedelta

import pytest

from ledgerline.events import webhooks
from ledgerline.payments.dunning import parse_retry_schedule


class TestRetrySchedule:
    def test_parses_days(self):
        assert parse_retry_schedule("3,5,7") == [3, 5, 7]
        assert parse_retry_schedule(" 1 , 2 ,") == [1, 2]
        assert parse_retry_schedule("") == []
        assert parse_retry_schedule(None) == []

    @pytest.mark.parametrize("spec", ["0", "31", "a,b", "1,1,1,1,1,1,1,1,1"])
    def test_rejects_invalid(self, spec):
        with pytest.raises(ValueError):
            parse_retry_schedule(spec)


class TestSignatures:
    secret = "whsec_test"
    body = '{"id": "evt_1"}'

    def test_round_trip(self):
        header = webhooks.signature_header(self.secret, 1591012800, self.body)
        assert header.startswith("t=1591012800,v1=")
        assert webhooks.verify_signature(header, self.secret, self.body, 1591012800)

    def test_rejects_tampered_body(self):
        header = webhooks.signature_header(self.secret, 1591012800, self.body)
        assert not webhooks.verify_signature(header, self.secret, self.body + " ", 1591012800)

    def test_rejects_wrong_secret(self):
        header = webhooks.signature_header(self.secret, 1591012800, self.body)
        assert not webhooks.verify_signature(header, "whsec_other", self.body, 1591012800)

    def test_rejects_old_signatures(self):
        header = webhooks.signature_header(self.secret, 1591012800, self.body)
        assert not webhooks.verify_signature(header, self.secret, self.body, 1591012800 + 301)

    def test_rejects_malformed_header(self):
        assert not webhooks.verify_signature("garbage", self.secret, self.body, 0)


@pytest.mark.parametrize(
    "attempts,expected",
    [
        (1, timedelta(minutes=1)),
        (2, timedelta(minutes=2)),
        (5, timedelta(minutes=16)),
        (9, timedelta(hours=4, minutes=16)),
        (10, timedelta(hours=6)),
        (30, timedelta(hours=6)),
    ],
)
def test_backoff(attempts, expected):
    assert webhooks.backoff(attempts) == expected
