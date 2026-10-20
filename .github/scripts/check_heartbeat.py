"""Fail when the pipeline's heartbeat is missing, too old, or reports a failure.

Run by the daily watchdog workflow. The pipeline uploads a small `heartbeat.json` after every
daily run; a server that has died can't send an alert itself, so this check, running elsewhere,
turns the silence into a failed workflow, and GitHub emails the failure.

The address is a read-only link to that one file, kept as a repository secret (HEARTBEAT_URL).
Standard library only; runs on the runner's own Python.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta

# The pipeline runs daily at 13:00 Greek time (10:00 or 11:00 UTC) and this check at 13:00 UTC,
# so a healthy heartbeat is 2-3 hours old here. One missed day makes it at least 26 hours old.
MAX_AGE = timedelta(hours=25)
GOOD = {"ok", "not-due"}


def verdict(beat: dict, now: datetime) -> str | None:
    """None if the heartbeat is fine, else what is wrong."""
    when = beat.get("finished") or beat.get("started")
    if not when:
        return "the heartbeat has no time"
    age = now - datetime.fromisoformat(when.replace("Z", "+00:00"))
    if age > MAX_AGE:
        return f"the last run was {age.total_seconds() / 3600:.0f} hours ago ({when})"
    if beat.get("result") not in GOOD:
        return f"the last run ({when}) ended with '{beat.get('result')}', failures: {beat.get('failures')}"
    return None


def main() -> int:
    url = os.environ.get("HEARTBEAT_URL")
    if not url:
        print("HEARTBEAT_URL is not set")
        return 1
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            beat = json.loads(resp.read())
    except (urllib.error.URLError, OSError, ValueError) as exc:
        print(f"Could not read the heartbeat: {exc}")
        return 1
    problem = verdict(beat, datetime.now(UTC))
    print(problem or f"OK: last run {beat.get('finished') or beat.get('started')}, result {beat.get('result')}")
    return 1 if problem else 0


if __name__ == "__main__":
    sys.exit(main())
