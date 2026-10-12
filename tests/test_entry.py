"""Tests for entry parsing and assembly."""

# pylint: disable=missing-function-docstring

from pyqtpass.entry import build_entry, parse_entry


def test_template_fields():
    content = "pw\nlogin: me\nurl: https://example.org\nfree text\n"
    parsed = parse_entry(content, ["login", "url"])
    assert parsed.password == "pw"
    assert parsed.fields == [("login", "me"), ("url", "https://example.org")]
    assert parsed.remaining == "free text"


def test_all_fields_skips_urls_without_name():
    parsed = parse_entry("pw\nuser: a\nhttps://x.org\nnote: b", (), True)
    assert parsed.fields == [("user", "a"), ("note", "b")]
    assert parsed.remaining == "https://x.org"


def test_otp_hidden_from_display():
    uri = "otpauth://totp/x?secret=GEZDGNBV"
    parsed = parse_entry(f"pw\n{uri}\nnote")
    assert parsed.otp == uri
    assert parsed.remaining == f"{uri}\nnote"
    assert parsed.remaining_display == "note"
    parsed = parse_entry("pw\notp: GEZDGNBV\nnote")
    assert parsed.otp == "GEZDGNBV"
    assert parsed.remaining_display == "note"
    parsed = parse_entry(uri)
    assert parsed.otp == uri and parsed.password_for_display == ""


def test_round_trip():
    content = build_entry("pw", [("login", "me"), ("url", "")], "free\n")
    assert content == "pw\nlogin: me\nfree\n"
    parsed = parse_entry(content, ["login"])
    assert build_entry(parsed.password, parsed.fields, parsed.remaining) == content


def test_field_rows_keep_duplicates():
    """Repeated fields each get an input, template fields come first."""
    from pyqtpass.fields_editor import (  # pylint: disable=import-outside-toplevel
        field_rows,
    )

    rows = field_rows(["login", "url"], [("url", "a"), ("note", "n"), ("url", "b")])
    assert rows == [
        ("login", "", True),
        ("url", "a", True),
        ("note", "n", False),
        ("url", "b", False),
    ]
