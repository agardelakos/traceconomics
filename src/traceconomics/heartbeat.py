"""After every run, report that it ran: a small JSON file uploaded to a fixed address.

A machine that dies can't send an alert, so something else has to notice the silence. Each run
(also a day with no release) uploads `heartbeat.json`; a separate daily check elsewhere reads it
and raises an alert when it is too old or reports a failure.

The address is a pre-authenticated upload URL for one object in private storage. It is a secret,
so it comes only from the environment. Without it, nothing is sent. The file holds no secrets:
run time, result and counts.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

URL_ENV = "TRACECONOMICS_HEARTBEAT_URL"
FIELDS = ("started", "finished", "result", "reason", "stored", "unchanged", "failures", "alerts")


def payload(record: dict) -> bytes:
    beat = {k: record[k] for k in FIELDS if k in record}
    if isinstance(beat.get("failures"), list):
        beat["failures"] = len(beat["failures"])
    return json.dumps(beat, indent=2, sort_keys=True).encode("utf-8")


def send(record: dict, *, url: str | None = None, timeout: float = 30.0) -> str:
    """Upload the heartbeat. Returns "sent", "off" (no URL configured) or "failed: <reason>"."""
    url = url or os.environ.get(URL_ENV)
    if not url:
        return "off"
    req = urllib.request.Request(url, data=payload(record), method="PUT",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp.read()
        return "sent"
    except (urllib.error.URLError, OSError) as exc:
        return f"failed: {exc}"
