"""The site's security.txt (site/public/.well-known/security.txt) follows RFC 9116 and agrees with
SECURITY.md. SECURITY.md is the one place for the reporting policy; security.txt only links to it.
The contacts are the one thing written in both, so they must match: a contact changed in one file
alone would send researchers to an address nobody reads.

The expiry date is not compared with today here (a test must not start failing on a calendar date);
the site checks warn as it nears, and renewing it is a yearly task."""

import re
from datetime import datetime
from pathlib import Path

import pytest

pytestmark = pytest.mark.repository

ROOT = Path(__file__).resolve().parent.parent
SECURITY_TXT = ROOT / "site" / "public" / ".well-known" / "security.txt"
SECURITY_MD = ROOT / "SECURITY.md"
PUBLISHED = "https://traceconomics.com/.well-known/security.txt"
REPOSITORY = "https://github.com/agardelakos/traceconomics"


def fields() -> list[tuple[str, str]]:
    """Each field line as (name, value), in order; comments and blank lines skipped."""
    out = []
    for line in SECURITY_TXT.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        name, sep, value = line.partition(": ")
        assert sep and re.fullmatch(r"[A-Za-z-]+", name), f"not a field line: {line!r}"
        out.append((name.lower(), value.strip()))
    return out


def values(name: str) -> list[str]:
    return [v for n, v in fields() if n == name]


def test_follows_rfc_9116():
    """PY-SECTXT-001: security.txt has the fields RFC 9116 requires, in its format

    Given the site's security.txt
    When its lines are read as fields
    Then every line that isn't a comment is a field
    And it has at least one Contact, each an https or mailto address
    And it has exactly one Expires, a date and time with a time zone
    And its Canonical is the address it is published at
    """
    contacts = values("contact")
    assert contacts and all(c.startswith(("https://", "mailto:")) for c in contacts), contacts
    expires = values("expires")
    assert len(expires) == 1, expires
    assert datetime.fromisoformat(expires[0]).tzinfo is not None, expires[0]
    assert values("canonical") == [PUBLISHED]


def test_contacts_match_security_md():
    """PY-SECTXT-002: security.txt and SECURITY.md name the same contacts

    Given the site's security.txt and the repository's SECURITY.md
    When the contacts of each are collected (security.txt's Contact fields; SECURITY.md's email addresses and private reporting link)
    Then both name the same contacts
    """
    in_txt = {c.removeprefix("mailto:") for c in values("contact")}
    text = SECURITY_MD.read_text(encoding="utf-8")
    in_md = set(re.findall(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", text))
    in_md |= set(re.findall(r"https://github\.com/[\w./-]+/security/advisories/new", text))
    assert in_txt == in_md


def test_policy_is_security_md():
    """PY-SECTXT-003: security.txt's policy is SECURITY.md

    Given the site's security.txt
    When its Policy field is read
    Then it is SECURITY.md on the repository's default branch, a file that exists
    """
    assert values("policy") == [f"{REPOSITORY}/blob/main/SECURITY.md"]
    assert SECURITY_MD.is_file()
