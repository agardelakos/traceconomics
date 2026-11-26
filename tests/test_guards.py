"""The harness tested: each guard behind a hard rule fires when the rule is broken.

A guard that has quietly stopped working looks exactly like a clean repository, so every guard gets
a test that plants a violation (in a temporary copy, never in the repository) and checks that the
guard refuses it with a message naming the rule. Addresses used: 192.0.2.1 is TEST-NET-1 (RFC 5737)
and `.invalid` never resolves (RFC 2606), so even a broken guard sends nothing anywhere real.
"""

import re
import shutil
import socket
import subprocess
import sys
import urllib.request
from pathlib import Path

import guards
import pytest
from guards import RULE, NetworkBlocked, NetworkGuard, is_local
from test_fixtures import ROW, changed
from test_lock_files import LOCKS, problems as lock_problems

pytestmark = pytest.mark.repository

HERE = Path(__file__).parent
ROOT = HERE.parent
RUFF = Path(sys.executable).parent / "ruff"  # pinned in requirements-dev.txt, beside this Python
# Planted text is put together from pieces, so this file holds no hit of its own.
AT, HOME, PRIVATE_DIR = "@", "/ho" + "me/", "do" + "cs/"


def test_a_connection_to_another_host_is_refused(monkeypatch):
    """PY-GUARD-001: A connection to another machine is refused, recorded, and named as a rule break

    Given the network guard on
    When a test opens a connection to an address that isn't this machine
    Then the call raises NetworkBlocked before anything is sent
    And the guard records the attempt, and its message names the rule
    """
    guard = NetworkGuard(monkeypatch)
    with pytest.raises(NetworkBlocked, match="AGENTS.md"):
        socket.create_connection(("192.0.2.1", 80), timeout=0.1)
    with socket.socket() as s, pytest.raises(NetworkBlocked):
        s.connect(("192.0.2.1", 80))
    assert len(guard.attempts) == 2
    assert RULE in guard.problem()


def test_a_swallowed_refusal_still_fails_the_test(monkeypatch):
    """PY-GUARD-002: Code that catches every exception can't hide a refused call

    Given the network guard on
    When code under test calls a named host and swallows whatever goes wrong
    Then the guard still holds the attempt, so the test fails at teardown
    """
    guard = NetworkGuard(monkeypatch)
    try:
        urllib.request.urlopen("http://example.invalid/", timeout=0.1)
    except Exception:  # the point: code under test may swallow everything
        pass
    assert guard.attempts == ["name lookup of 'example.invalid'"]
    assert guard.problem() is not None


def test_this_machine_stays_allowed(monkeypatch):
    """PY-GUARD-003: A server the test started on this machine can still be reached

    Given the network guard on and a listening socket on 127.0.0.1
    When the test connects to it, by address and as localhost
    Then both connections succeed and nothing is recorded
    And loopback addresses, `localhost` and no host count as this machine; others don't
    """
    guard = NetworkGuard(monkeypatch)
    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        server.listen()
        port = server.getsockname()[1]
        socket.create_connection(("127.0.0.1", port), timeout=1).close()
        socket.create_connection(("localhost", port), timeout=1).close()
    assert guard.attempts == []
    assert all(is_local(h) for h in ["127.0.0.1", "127.8.9.1", "::1", "[::1]", "localhost", "LOCALHOST", None, ""])
    assert not any(is_local(h) for h in ["192.0.2.1", "10.0.0.1", "example.org", "0.0.0.0", "::"])


def test_the_conftest_switches_the_guard_on_for_every_test(tmp_path):
    """PY-GUARD-004: In a real run, a test that reaches the network fails, even if it hides the error

    Given a throwaway project with a copy of the suite's conftest and guard
    When pytest runs a test that calls another host and catches the error, and one that doesn't call out
    Then the first fails with the rule in its message and the second passes
    """
    for name in ("conftest.py", "guards.py"):
        shutil.copy(HERE / name, tmp_path / name)
    (tmp_path / "pyproject.toml").write_text(
        '[tool.pytest.ini_options]\nmarkers = ["unit: u", "integration: i", "repository: r"]\n',
        encoding="utf-8",
        newline="\n",
    )
    (tmp_path / "test_planted.py").write_text(
        "import urllib.request\n\nimport pytest\n\npytestmark = pytest.mark.unit\n\n\n"
        "def test_calls_out():\n"
        "    try:\n"
        "        urllib.request.urlopen('http://192.0.2.1/', timeout=0.1)\n"
        "    except Exception:\n"
        "        pass\n\n\n"
        "def test_stays_here():\n"
        "    assert True\n",
        encoding="utf-8",
        newline="\n",
    )
    done = subprocess.run(
        [sys.executable, "-I", "-m", "pytest", "-p", "no:cacheprovider", "-p", "no:xdist", "-rA"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert done.returncode == pytest.ExitCode.TESTS_FAILED, done.stdout + done.stderr
    assert "ERROR test_planted.py::test_calls_out" in done.stdout
    assert "PASSED test_planted.py::test_stays_here" in done.stdout
    assert "tests never call the network" in done.stdout


def ruff_on(source: str, path: str) -> subprocess.CompletedProcess:
    """Ruff's banned-import rule, with the project's settings, on source as if it lived at path."""
    return subprocess.run(
        [str(RUFF), "check", "--select", "TID251", "--stdin-filename", path, "-"],
        cwd=ROOT,
        input=source,
        capture_output=True,
        text=True,
    )


def test_pandas_and_numpy_are_refused_outside_the_microdata_code():
    """PY-GUARD-005: Lint refuses pandas or numpy anywhere but the microdata code

    Given the project's Ruff settings
    When a module outside src/traceconomics/local/, or a new test file, imports pandas or numpy
    Then Ruff fails, naming the rule and where they belong
    And the same import inside src/traceconomics/local/ passes
    """
    planted = "import pandas as pd\nfrom numpy import array\n"
    for path in ["src/traceconomics/engine/planted.py", "tests/test_planted.py"]:
        done = ruff_on(planted, path)
        assert done.returncode == 1, done.stdout
        assert done.stdout.count("TID251") == 2 and "only in src/traceconomics/local/" in done.stdout
    assert ruff_on(planted, "src/traceconomics/local/planted.py").returncode == 0


def test_private_text_in_a_file_is_found(tmp_path):
    """PY-GUARD-006: Each kind of private text planted in a file is found, and public text is not

    Given a file holding an e-mail address, a local path, a decision number, a private link and a name
    When the private-text guard scans it, with that name on its list
    Then each is reported with its file, line and kind
    And the project's address, example.org, a decile (D10), a URL path and the repository's URL are not
    """
    (tmp_path / "planted.py").write_text(
        f"# ask someone{AT}mail.gr\n"
        f"# built in {HOME}someone/project\n"
        "# as agreed in D1" + "42\n"
        f"# see {PRIVATE_DIR}plan.md\n"
        "# written by Jane Planted\n",
        encoding="utf-8",
    )
    (tmp_path / "public.py").write_text(
        f"# support{AT}traceconomics.com, you{AT}example.org, the top decile D10\n"
        f"# https://playwright.dev/{PRIVATE_DIR}test-cli, https://github.com/Planted/traceconomics\n",
        encoding="utf-8",
    )
    found = guards.private_text(tmp_path, ["planted.py", "public.py"], [], names=["planted"])
    assert [h.split(" (")[0] for h in found] == [
        "planted.py:3: a decision number",
        "planted.py:4: a link to private notes",
        "planted.py:2: a local path",
        "planted.py:1: an e-mail address",
        "planted.py:5: a personal name",
    ]


def test_an_allow_entry_covers_one_kind_and_must_stay_needed(tmp_path):
    """PY-GUARD-007: An allow entry excuses one kind of hit in one file, and fails once nothing needs it

    Given a file with a local path, and allow entries for it, for another kind, and for a missing file
    When the guard scans and checks the allow list
    Then the local path is excused and nothing else is
    And the entry for a kind the file doesn't have, and the one for a missing file, are reported stale
    """
    (tmp_path / "a.py").write_text(f"PATTERN = '{HOME}'\n", encoding="utf-8")
    allow = [
        {"path": "a.py", "what": "a local path", "reason": "holds the pattern"},
        {"path": "a.py", "what": "an e-mail address", "reason": "none left"},
        {"path": "gone.py", "what": "a local path", "reason": "file removed"},
    ]
    assert guards.private_text(tmp_path, ["a.py"], allow) == []
    assert guards.private_text(tmp_path, ["a.py"], []) != []
    assert guards.stale_allows(tmp_path, ["a.py"], allow) == [
        "a.py: an e-mail address no longer found; remove its entry",
        "gone.py: no such tracked file",
    ]


def test_a_new_skip_fails_until_it_is_listed(tmp_path):
    """PY-GUARD-008: A skip added to a test fails the ratchet, and so does a listed one that's gone

    Given a Python test and a Playwright test, each with skips, and a list that covers only some
    When the skips are counted and compared with the list
    Then the unlisted ones are reported with the rule and what to do
    And a listed skip that no longer exists is reported too, and `importorskip` is never counted
    """
    mark, call = "pytest.mark." + "skip", "test." + "fixme("
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_a.py").write_text(
        f"@{mark}(reason='flaky')\ndef test_a():\n    pass\n\n" + "pytest." + "importorskip('pandas')\n",
        encoding="utf-8",
    )
    (tmp_path / "site/tests/ui").mkdir(parents=True)
    (tmp_path / "site/tests/ui/b.ui.ts").write_text(f"{call}'later');\n{call}'later');\n", encoding="utf-8")
    counts = guards.skip_counts(tmp_path, ["tests/test_a.py", "site/tests/ui/b.ui.ts", "notes.py"])
    assert counts == {("tests/test_a.py", "pytest.mark.skip"): 1, ("site/tests/ui/b.ui.ts", "test.fixme()"): 2}
    listed = [
        {"path": "site/tests/ui/b.ui.ts", "kind": "test.fixme()", "count": 1, "reason": "r"},
        {"path": "tests/test_gone.py", "kind": "pytest.mark.xfail", "count": 1, "reason": "r"},
    ]
    found = guards.skip_problems(counts, listed)
    assert len(found) == 3
    assert found[0].startswith("site/tests/ui/b.ui.ts: 2 × test.fixme(), the list has 1") and "AGENTS.md" in found[0]
    assert found[1].startswith("tests/test_a.py: 1 × pytest.mark.skip, the list has 0")
    assert found[2].startswith("tests/test_gone.py: 0 × pytest.mark.xfail, the list has 1: lower the count")
    assert guards.skip_problems(
        counts, listed[:1] + [{"path": "tests/test_a.py", "kind": "pytest.mark.skip", "count": 1}]
    ) == [found[0]]


def test_an_edited_fixture_fails_its_hash_check(tmp_path):
    """PY-GUARD-009: A publisher's file edited, re-saved with other line endings, or removed is found

    Given a copy of one untouched fixture and its README row with the published SHA-256
    When the copy is unchanged, then has one byte changed, then its line endings converted, then is gone
    Then only the unchanged copy passes the fixtures' hash check
    """
    row = next(
        line for line in (HERE / "fixtures/README.md").read_text(encoding="utf-8").splitlines() if ROW.match(line)
    )
    name = ROW.match(row)[1]
    (tmp_path / "README.md").write_text(row + "\n", encoding="utf-8")
    data = (HERE / "fixtures" / name).read_bytes()
    target = tmp_path / name
    target.write_bytes(data)
    assert changed(tmp_path) == []
    target.write_bytes(data[:-1] + bytes([data[-1] ^ 1]))
    assert changed(tmp_path) == [name]
    target.write_bytes(data.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
    assert changed(tmp_path) == ([name] if b"\n" in data else [])
    target.unlink()
    assert changed(tmp_path) == [name]


def test_a_pin_changed_without_its_lock_files_is_found(tmp_path):
    """PY-GUARD-010: A dependency changed in pyproject.toml without regenerating the locks is found

    Given copies of pyproject.toml and the four lock files
    When the copies are unchanged, then one base pin is changed in pyproject.toml, then a lock line loses its hash
    Then the unchanged copies pass
    And the changed pin is reported for every lock file, and the line without a hash for its file
    """
    for name in ["pyproject.toml"] + [n for n, _ in LOCKS]:
        shutil.copy(ROOT / name, tmp_path / name)
    assert lock_problems(tmp_path) == []
    pyproject = (tmp_path / "pyproject.toml").read_text(encoding="utf-8")
    pin = re.search(r'"(duckdb)==([^"]+)"', pyproject)
    (tmp_path / "pyproject.toml").write_text(pyproject.replace(pin[0], f'"duckdb=={pin[2]}.1"'), encoding="utf-8")
    found = lock_problems(tmp_path)
    assert [p.split(":")[0] for p in found] == [n for n, _ in LOCKS]
    assert all(f"duckdb {pin[2]}, pyproject {pin[2]}.1" in p for p in found)
    shutil.copy(ROOT / "pyproject.toml", tmp_path / "pyproject.toml")
    lock = (tmp_path / "requirements-dev.txt").read_text(encoding="utf-8")
    (tmp_path / "requirements-dev.txt").write_text(
        re.sub(r"(?m)^duckdb==\S+.*\\\n(\s+--hash=\S+\s*\\?\n)+", f"duckdb=={pin[2]}\n", lock, count=1),
        encoding="utf-8",
    )
    assert lock_problems(tmp_path) == ["requirements-dev.txt: no hash for duckdb==" + pin[2]]
