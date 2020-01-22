import pytest

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
