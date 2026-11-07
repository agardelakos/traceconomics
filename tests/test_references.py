"""The bibliography stays well-formed: unique keys, and every entry can be found and dated."""

import re

import pytest

from traceconomics import references

pytestmark = pytest.mark.unit

KEY = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def test_keys_are_unique_and_tidy():
    """PY-REFS-001: the bibliography's keys are many and tidy

    Given the project's bibliography
    When its entries are read
    Then there are at least 40
    And every key is lower-case words joined by hyphens
    """
    entries = references.entries()
    assert len(entries) >= 40
    bad = [k for k in entries if not KEY.match(k)]
    assert not bad, f"keys should be lower-case words joined by hyphens: {bad}"


def test_every_entry_has_a_title_and_a_way_to_find_it():
    """PY-REFS-002: every entry has a title, an author and a way to find it

    Given the project's bibliography
    When each entry is checked
    Then it has a title, an author and a URL or DOI
    And an entry with a URL has the date it was checked
    """
    for key, e in references.entries().items():
        assert "title" in e.fields, key
        assert "author" in e.fields, key
        assert {"url", "doi"} & e.fields, f"{key}: no url or doi"
        if "url" in e.fields:
            assert "urldate" in e.fields, f"{key}: a web address needs the date it was checked"


def test_braces_balance():
    """PY-REFS-003: the braces balance

    Given the bibliography's text
    When its braces are counted in order
    Then the depth never goes below zero
    And it ends at zero
    """
    depth = 0
    for ch in references.text():
        depth += {"{": 1, "}": -1}.get(ch, 0)
        assert depth >= 0
    assert depth == 0


def test_missing_keys_are_reported():
    """PY-REFS-004: missing citation keys are reported

    Given two keys in the bibliography and one that isn't
    When the missing keys are asked for
    Then only the unknown key is returned
    """
    assert references.missing(["hicp-manual-2024", "no-such-source", "reg-2020-1148"]) == ["no-such-source"]
