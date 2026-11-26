"""The skip ratchet: every skip, skipif, xfail, `test.skip` and `test.fixme` in the test code is on the
reviewed list `tests/skips.toml`, with its reason, and the list holds nothing that is gone. A test is
never skipped to make a run pass; a skip that depends on the run (data, a build, a server) is listed."""

import tomllib
from pathlib import Path

import pytest
from guards import skip_counts, skip_problems, tracked_files

pytestmark = pytest.mark.repository

ROOT = Path(__file__).resolve().parent.parent


def test_every_skip_is_on_the_reviewed_list():
    """PY-SKIPS-001: The skips in the test code are exactly the reviewed list, each with its reason

    Given every tracked or new test file, Python and TypeScript
    When their skips are counted per file and kind
    Then the counts equal tests/skips.toml's, entry for entry
    And every entry gives its reason
    """
    listed = tomllib.loads((ROOT / "tests/skips.toml").read_text(encoding="utf-8"))["skip"]
    assert skip_problems(skip_counts(ROOT, tracked_files(ROOT)), listed) == []
    assert all(e.get("reason", "").strip() for e in listed)
