"""Nothing private or internal in the repository's own files: no personal names, e-mail addresses
or local paths, no decision numbers or links to private notes, in any tracked file but where
`tests/private_text.toml` expects one, with its reason. Site check 3 checks the built pages; this
checks the source they and everything else are made from."""

import os
import re
import tomllib
from pathlib import Path

import pytest
from guards import PRIVATE, private_text, stale_allows, tracked_files

pytestmark = pytest.mark.repository

ROOT = Path(__file__).resolve().parent.parent
ALLOW = tomllib.loads((ROOT / "tests/private_text.toml").read_text(encoding="utf-8"))["allow"]
# The names to look for are the private part: kept outside the repository, comma-separated.
NAMES = "TRACECONOMICS_PRIVATE_NAMES"


def test_no_private_text_in_tracked_files():
    """PY-PRIVATE-001: No tracked file holds an e-mail address, local path, decision number or private link

    Given every file git tracks, but the publishers' files in tests/fixtures/
    When each is scanned for the private patterns
    Then nothing is found that the allow list doesn't expect
    And every allow entry still covers a hit, names a known kind and gives its reason
    """
    files = tracked_files(ROOT)
    assert private_text(ROOT, files, ALLOW) == []
    assert stale_allows(ROOT, files, ALLOW) == []
    kinds = set(PRIVATE) | {"a personal name"}
    assert all(a["what"] in kinds and a.get("reason", "").strip() for a in ALLOW)


@pytest.mark.skipif(not os.environ.get(NAMES), reason=f"{NAMES} not set: the names are kept outside the repository")
def test_no_personal_names_in_tracked_files():
    """PY-PRIVATE-002: No tracked file names the people behind the project, except where it must

    Given the names to look for, from an environment variable kept outside the repository
    When every tracked file is scanned for them (the repository's own GitHub address aside)
    Then they appear only where the allow list says, such as the licence and the citation file
    """
    names = [n.strip() for n in os.environ[NAMES].split(",") if n.strip()]
    hits = private_text(ROOT, tracked_files(ROOT), ALLOW, names)
    assert [h for h in hits if ": a personal name (" in h] == []


def test_site_check_3_refuses_the_same_kinds():
    """PY-PRIVATE-003: The built pages are checked for the same kinds of private text as the source

    Given site check 3 in site/scripts/checks.mjs
    When its list of refused kinds is read
    Then it is exactly this guard's list, so the two can't drift apart
    """
    text = (ROOT / "site/scripts/checks.mjs").read_text(encoding="utf-8")
    block = re.search(r"// Nothing private or internal in the text\.(.*?)\]\) \{", text, re.S)
    assert block, "site check 3's pattern list not found in checks.mjs"
    assert re.findall(r'/, "([^"]+)"\]', block.group(1)) == list(PRIVATE)
