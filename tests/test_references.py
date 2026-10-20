"""The bibliography stays well-formed: unique keys, and every entry can be found and dated."""

import re

from traceconomics import references

KEY = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def test_keys_are_unique_and_tidy():
    entries = references.entries()
    assert len(entries) >= 40
    bad = [k for k in entries if not KEY.match(k)]
    assert not bad, f"keys should be lower-case words joined by hyphens: {bad}"


def test_every_entry_has_a_title_and_a_way_to_find_it():
    for key, e in references.entries().items():
        assert "title" in e.fields, key
        assert "author" in e.fields, key
        assert {"url", "doi"} & e.fields, f"{key}: no url or doi"
        if "url" in e.fields:
            assert "urldate" in e.fields, f"{key}: a web address needs the date it was checked"


def test_braces_balance():
    depth = 0
    for ch in references.text():
        depth += {"{": 1, "}": -1}.get(ch, 0)
        assert depth >= 0
    assert depth == 0


def test_missing_keys_are_reported():
    assert references.missing(["hicp-manual-2024", "no-such-source", "reg-2020-1148"]) == ["no-such-source"]
