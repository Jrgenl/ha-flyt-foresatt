"""Tests for the API helpers."""

from datetime import date

from custom_components.flyt_foresatt.api import format_date, parse_cookie_header


def test_parse_cookie_header() -> None:
    """Pasted cookie headers are parsed leniently."""
    assert parse_cookie_header("Cookie: a=1; b=x=y ;\n c=3") == {
        "a": "1",
        "b": "x=y",
        "c": "3",
    }
    assert parse_cookie_header("  ") == {}
    assert parse_cookie_header("garbage") == {}


def test_format_date() -> None:
    """Dates use the portal's ISO-like format."""
    assert format_date(date(2026, 9, 28)) == "2026-09-28T00:00:00"
