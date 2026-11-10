"""The untouched fixtures are still byte-identical to what the publishers served.

Their hashes are listed in tests/fixtures/README.md. A mismatch means a file was edited or
re-saved, or line endings were converted on checkout."""

import hashlib
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.repository

FIXTURES = Path(__file__).parent / "fixtures"
ROW = re.compile(r"^\| `([^`]+)` \| `([0-9a-f]{64})` \|$")


def listed() -> dict[str, str]:
    text = (FIXTURES / "README.md").read_text(encoding="utf-8")
    return {m[1]: m[2] for line in text.splitlines() if (m := ROW.match(line))}


def test_untouched_fixtures_match_their_published_hashes():
    """PY-FIXT-001: the untouched fixtures match their listed hashes

    Given the fixtures README, which lists the SHA-256 of each untouched fixture
    When each listed file is hashed
    Then exactly 10 files are listed
    And every file's SHA-256 matches the one listed
    """
    hashes = listed()
    assert len(hashes) == 10
    for name, expected in hashes.items():
        assert hashlib.sha256((FIXTURES / name).read_bytes()).hexdigest() == expected, name
