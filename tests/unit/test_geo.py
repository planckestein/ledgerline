import json

import pytest

from ledgerline.geo import is_eu, normalize_country, parse_legacy_address, serialize_address


@pytest.mark.parametrize(
    "value,expected",
    [
        ("de", "DE"),
        (" DE ", "DE"),
        ("Germany", "DE"),
        ("deutschland", "DE"),
        ("UK", "GB"),
        ("EL", "GR"),
        ("United States of America", "US"),
        ("Atlantis", None),
        ("", None),
        (None, None),
    ],
)
def test_normalize_country(value, expected):
    assert normalize_country(value) == expected


def test_is_eu():
    assert is_eu("FR")
    assert not is_eu("GB")
    assert not is_eu(None)


class TestParseLegacyAddress:
    def test_v1_dashboard_format(self):
        raw = json.dumps({"street": "Unter den Linden 1", "zip": "10117", "country": "Germany"})
        assert parse_legacy_address(raw) == {
            "line1": "Unter den Linden 1",
            "line2": None,
            "city": None,
            "state": None,
            "postal_code": "10117",
            "country": "DE",
        }

    def test_v2_api_format(self):
        raw = json.dumps(
            {
                "line1": "1 Main St",
                "line2": "Suite 5",
                "city": "Springfield",
                "state": "IL",
                "postal_code": "62701",
                "country": "us",
            }
        )
        address = parse_legacy_address(raw)
        assert address["country"] == "US"
        assert address["state"] == "IL"
        assert address["line2"] == "Suite 5"

    def test_country_code_key(self):
        assert parse_legacy_address('{"country_code": "fr"}')["country"] == "FR"

    def test_v3_importer_string(self):
        address = parse_legacy_address("Hauptstr. 5, 10115 Berlin, DE")
        assert address == {
            "line1": "Hauptstr. 5",
            "line2": None,
            "city": "Berlin",
            "state": None,
            "postal_code": "10115",
            "country": "DE",
        }

    def test_v3_with_extra_segments(self):
        address = parse_legacy_address("Keizersgracht 1, 2nd floor, 1015 CJ Amsterdam, Netherlands")
        assert address["line1"] == "Keizersgracht 1"
        assert address["line2"] == "2nd floor"
        assert address["postal_code"] == "1015"
        assert address["city"] == "CJ Amsterdam"
        assert address["country"] == "NL"

    def test_v3_double_encoded(self):
        raw = json.dumps("Rue de Rivoli 10, 75001 Paris, FR")
        assert parse_legacy_address(raw)["country"] == "FR"

    def test_v3_without_country(self):
        address = parse_legacy_address("Somewhere 1, Springfield")
        assert address["country"] is None
        assert address["city"] == "Springfield"

    @pytest.mark.parametrize("raw", [None, "", "   ", "null", "[]", "42", "{}"])
    def test_empty_values(self, raw):
        assert set(parse_legacy_address(raw).values()) == {None}

    def test_blank_strings_become_none(self):
        assert parse_legacy_address('{"line1": "  ", "country": ""}')["line1"] is None


def test_serialize_address_round_trip():
    raw = serialize_address({"line1": "1 Main St", "country": "us", "city": None})
    assert json.loads(raw) == {"line1": "1 Main St", "country": "US"}
    assert parse_legacy_address(raw)["country"] == "US"
    assert serialize_address({}) is None
    assert serialize_address(None) is None
