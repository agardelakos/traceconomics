"""Sensors behind the hard rules in `AGENTS.md`, shared by the suite and the tests that prove them.

The network sensor: a test never reaches the network (`AGENTS.md`, hard rules). A test may talk to a
server it started itself on this machine (127.0.0.1, ::1, `localhost`), since nothing leaves the
machine; anything else is refused. `tests/conftest.py` switches the sensor on for every measured test.

A refused call raises `NetworkBlocked`, and the attempt is also recorded, because code under test may
catch every exception (the heartbeat turns any failure into a "failed: ..." result) and the test would
then pass without ever showing the call; conftest fails such a test at teardown from the record.

The private-text sensor (below) scans the repository's tracked files; `tests/test_private_text.py`
runs it, with its allow list in `tests/private_text.toml`.
"""

from __future__ import annotations

import ipaddress
import re
import socket
import subprocess
from pathlib import Path

RULE = "tests never call the network (AGENTS.md, hard rules): use a saved fixture or a server on 127.0.0.1"
LOCAL_NAMES = {"localhost", "localhost.localdomain"}


class NetworkBlocked(RuntimeError):
    """A test tried to reach a host that isn't this machine."""


def is_local(host) -> bool:
    """True for this machine: a loopback address, `localhost`, or no host at all (a bind's lookup)."""
    if host is None or host == "":
        return True
    if isinstance(host, bytes):
        host = host.decode("ascii", "replace")
    host = str(host).strip("[]").split("%", 1)[0]  # an IPv6 literal may come bracketed or with a zone
    if host.lower() in LOCAL_NAMES:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


class NetworkSensor:
    """Patches the socket calls that reach another host; `attempts` lists what was refused."""

    def __init__(self, monkeypatch):
        self.attempts: list[str] = []
        real_connect = socket.socket.connect
        real_connect_ex = socket.socket.connect_ex
        real_getaddrinfo = socket.getaddrinfo
        sensor = self

        def check(what: str, host) -> None:
            if not is_local(host):
                sensor.attempts.append(f"{what} {host!r}")
                raise NetworkBlocked(f"{what} {host!r} refused: {RULE}")

        def host_of(sock, address):
            # Only internet sockets reach other machines; a Unix socket or a socket pair stays here.
            if sock.family in (socket.AF_INET, socket.AF_INET6) and isinstance(address, tuple):
                return address[0]
            return None

        def connect(sock, address):
            check("connect to", host_of(sock, address))
            return real_connect(sock, address)

        def connect_ex(sock, address):
            check("connect to", host_of(sock, address))
            return real_connect_ex(sock, address)

        def getaddrinfo(host, *args, **kwargs):
            check("name lookup of", host)
            return real_getaddrinfo(host, *args, **kwargs)

        monkeypatch.setattr(socket.socket, "connect", connect)
        monkeypatch.setattr(socket.socket, "connect_ex", connect_ex)
        monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)

    def problem(self) -> str | None:
        """The failure message when anything was refused, else None."""
        if not self.attempts:
            return None
        return "this test tried to reach the network: " + "; ".join(self.attempts) + f". {RULE}"


# The private-text sensor: nothing private or internal in the repository's own files (AGENTS.md, hard
# rules: no personal names, emails or local paths; decision numbers belong to private notes). The same
# kinds site check 3 (site/scripts/checks.mjs) refuses on the built pages, here on every tracked file.
# The patterns differ where source differs from page text: `D10` is a decile label, and `docs/` inside
# a URL is another site's path.
PRIVATE = {
    "a decision number": re.compile(r"\bD(?!10\b)\d{2,3}\b"),
    "a link to private notes": re.compile(r"(?<![\w./-])docs/"),
    "a local path": re.compile(r"[A-Za-z]:\\\\?Users|/home/|/Users/"),
    "an e-mail address": re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"),
}
# Addresses that are nobody's: the project's public one, and the domains kept for examples (RFC 2606).
PUBLIC_EMAIL = re.compile(r"support@traceconomics\.com|@example\.(org|com|net)\b|@[\w-]+\.invalid\b", re.I)
# Publishers' files, never edited (their own text is theirs), and the repository's own address.
NEVER_SCANNED = ("tests/fixtures/",)
REPO_URL = re.compile(r"github(usercontent)?\.com/[\w-]+/traceconomics")


def tracked_files(root: Path) -> list[str]:
    """The files git tracks under root, and new ones not ignored yet, as posix paths."""
    done = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )
    return sorted(p for p in done.stdout.split("\0") if p)


def private_text(root: Path, files: list[str], allow: list[dict], names: list[str] = ()) -> list[str]:
    """Every hit of a private pattern, or of one of `names`, not covered by an `allow` entry.

    An allow entry is {path, what, reason}: in that file, that kind of hit is expected (`what` is a key
    of PRIVATE, or "a personal name"). Binary files are skipped: they carry no text to read.
    """
    allowed = {(a["path"], a["what"]) for a in allow}
    kinds = dict(PRIVATE)
    if names:
        kinds["a personal name"] = re.compile(r"\b(" + "|".join(re.escape(n) for n in names) + r")\b", re.I)
    out = []
    for path in files:
        if path.startswith(NEVER_SCANNED):
            continue
        try:
            text = (root / path).read_text(encoding="utf-8")
        except UnicodeDecodeError, FileNotFoundError, IsADirectoryError:
            continue
        text = REPO_URL.sub("", PUBLIC_EMAIL.sub("", text))
        for what, pattern in kinds.items():
            if (path, what) in allowed:
                continue
            for n, line in enumerate(text.splitlines(), 1):
                if hit := pattern.search(line):
                    out.append(f"{path}:{n}: {what} ({hit.group(0)!r})")
    return out


def stale_allows(root: Path, files: list[str], allow: list[dict]) -> list[str]:
    """Allow entries that no longer cover a hit (or a file that's gone): the list may only shrink."""
    out = []
    for a in allow:
        if a["what"] == "a personal name":
            continue  # the names live outside the repository; their entries can't be checked here
        if a["path"] not in files:
            out.append(f"{a['path']}: no such tracked file")
        elif not any(
            f": {a['what']} (" in h for h in private_text(root, [a["path"]], [x for x in allow if x is not a])
        ):
            out.append(f"{a['path']}: {a['what']} no longer found; remove its entry")
    return out


# The skip ratchet: a test is never skipped or marked to fail to make a run pass (AGENTS.md, hard
# rules). Every skip in the test code is counted per file and kind, and the counts must equal the
# reviewed list in tests/skips.toml: a new skip fails until the list gains it, in the same diff a
# reviewer reads, and a removed one fails until the list shrinks. `pytest.importorskip` is a rule of
# the suite (tests needing the `local` extra), not a skip to pass, so it isn't counted.
SKIPS = {
    "pytest.mark.skip": re.compile(r"\bpytest\.mark\.skip\b(?!if)"),
    "pytest.mark.skipif": re.compile(r"\bpytest\.mark\.skipif\b"),
    "pytest.mark.xfail": re.compile(r"\bpytest\.mark\.xfail\b"),
    "pytest.skip()": re.compile(r"\bpytest\.skip\("),
    "pytest.xfail()": re.compile(r"\bpytest\.xfail\("),
    "test.skip()": re.compile(r"\b(test|it|describe)(\.describe)?\.skip\("),
    "test.fixme()": re.compile(r"\b(test|it|describe)(\.describe)?\.fixme\("),
    "test.fail()": re.compile(r"\b(test|it|describe)(\.describe)?\.fail\("),
    "test.todo()": re.compile(r"\b(test|it|describe)\.todo\("),
}
# The sensor and its tests are left out: they hold the kinds' names and planted skips as text.
SKIP_FILES = re.compile(
    r"^(tests/(?!fixtures/|sensors\.py$|test_sensors\.py$).*\.py|site/src/.*\.test\.ts|site/tests/.*\.ts)$"
)


def skip_counts(root: Path, files: list[str]) -> dict[tuple[str, str], int]:
    """How many skips of each kind each test file holds: {(path, kind): count}."""
    out = {}
    for path in files:
        if not SKIP_FILES.match(path) or not (root / path).is_file():
            continue
        text = (root / path).read_text(encoding="utf-8")
        for kind, pattern in SKIPS.items():
            if n := len(pattern.findall(text)):
                out[(path, kind)] = n
    return out


def skip_problems(counts: dict[tuple[str, str], int], listed: list[dict]) -> list[str]:
    """Where the counted skips and the reviewed list disagree, each with what to do."""
    want = {(e["path"], e["kind"]): e["count"] for e in listed}
    out = []
    for key in sorted(set(counts) | set(want)):
        have, should = counts.get(key, 0), want.get(key, 0)
        if have > should:
            out.append(
                f"{key[0]}: {have} × {key[1]}, the list has {should}. A test is never skipped to make a run "
                "pass (AGENTS.md, hard rules): fix the test, or add the skip to tests/skips.toml with its reason"
            )
        elif have < should:
            out.append(f"{key[0]}: {have} × {key[1]}, the list has {should}: lower the count in tests/skips.toml")
    return out
