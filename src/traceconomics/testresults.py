"""Release builds' browser-test results, sent to the test-results bucket for the public run history.

A release build runs the browser tests on real data (`ui-test` before its upload, `smoke` on the
preview) and checks each promote. Those are the runs that gate what the public sees, so they
belong in the project's test history next to CI's. This machine holds no credential for the code
repository: it uploads each result through a pre-authenticated link that can only write, and only
under `results/` (`TRACECONOMICS_TESTRESULTS_URL`, ending in `/o/`). A scheduled workflow reads
the bucket, checks every file and adds the runs to the history.

One folder per step run, `results/<build>/<step>-<started>/`: the suite's own JSON report
(`playwright.json`), then `meta.json`, written last, so a folder with a `meta.json` is complete.

Sending results is a report, not a gate: a failed upload never fails a build or a promote. It is
returned to the caller, which puts it in the release email.

Standard library only.
"""

from __future__ import annotations

import json
import os
import platform
import re
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

URL_ENV = "TRACECONOMICS_TESTRESULTS_URL"
STEPS = ("ui-test", "smoke", "promote")
COMMIT = re.compile(r"^[0-9a-f]{40}$")


def source_commit(repo: Path) -> str | None:
    """The commit the code at `repo` is checked out at, read from `.git` itself: the release
    image has no git. None when it can't be told (no checkout, a detached state we can't read)."""
    git = repo / ".git"
    try:
        head = (git / "HEAD").read_text(encoding="utf-8").strip()
        if COMMIT.match(head):
            return head
        ref = head.removeprefix("ref: ").strip()
        loose = git / ref
        if loose.is_file():
            value = loose.read_text(encoding="utf-8").strip()
            return value if COMMIT.match(value) else None
        for line in (git / "packed-refs").read_text(encoding="utf-8").splitlines():
            parts = line.split()
            if len(parts) == 2 and parts[1] == ref and COMMIT.match(parts[0]):
                return parts[0]
    except OSError:
        return None
    return None


def environment() -> dict[str, str]:
    return {"platform": f"{platform.system().lower()}-{platform.machine().lower()}", "data": "real",
            "runner": "release build"}


def _put(url: str, body: bytes, timeout: float) -> None:
    req = urllib.request.Request(url, data=body, method="PUT", headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:   # noqa: S310 (our own https link)
        resp.read()


def send(*, build: str, commit: str | None, step: str, started: datetime, result: str,
         results: Path | None = None, url: str | None = None, put: Callable[[str, bytes, float], None] = _put,
         timeout: float = 60.0) -> dict:
    """Upload one step run's results. Returns {"result": "off" | "ok" | "failed", …}; never raises."""
    url = (url if url is not None else os.environ.get(URL_ENV, "")).strip()
    if not url:
        return {"result": "off"}
    if not url.endswith("/o/"):
        return {"result": "failed", "error": f"{URL_ENV} should end in /o/"}
    if step not in STEPS or result not in ("passed", "failed"):
        return {"result": "failed", "error": f"unknown step or result: {step} {result}"}
    if not commit:
        return {"result": "failed", "error": "the build's commit is unknown"}
    at = started.strftime("%Y%m%dT%H%M%SZ")
    folder = f"results/{urllib.parse.quote(build)}/{step}-{at}/"
    meta = {"schema": 1, "build": build, "commit": commit, "step": step,
            "started": started.strftime("%Y-%m-%dT%H:%M:%SZ"), "environment": environment(), "result": result}
    try:
        if step != "promote":
            if results is None or not results.is_file():
                return {"result": "failed", "error": "no results file"}
            put(url + folder + "playwright.json", results.read_bytes(), timeout)
        put(url + folder + "meta.json", json.dumps(meta, indent=1).encode("utf-8"), timeout)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        # The message names the object, never the link (which works like a password).
        return {"result": "failed", "error": f"{folder}: {type(exc).__name__}: {getattr(exc, 'reason', exc)}"}
    return {"result": "ok", "folder": folder}
