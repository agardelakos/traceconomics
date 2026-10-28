"""Copy daily visit counts from Cloudflare Web Analytics into the raw archive, one file per UTC day.

Cloudflare keeps exact rows for 7 days, then only a sample, and lets the free plan query
184 days back; the archive keeps them for good. Each day is one JSON file under
`raw/cloudflare/web-analytics/`, with the day in its contents, so two quiet days are two files.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta

from traceconomics.archive.store import Archive, StoreResult, utc_now

TOKEN_ENV = "TRACECONOMICS_ANALYTICS_TOKEN"
ACCOUNT_ENV = "CLOUDFLARE_ACCOUNT_ID"
GRAPHQL_URL = "https://api.cloudflare.com/client/v4/graphql"
SOURCE = "cloudflare"
DATASET = "web-analytics"
HOSTS = ("traceconomics.com", "www.traceconomics.com")
PAGE = 10000
STATE_KEY = "analytics_through"

QUERY = """\
query ($account: string!, $day: Date!, $hosts: [string!]) { viewer { accounts(filter: {accountTag: $account}) {
  rumPageloadEventsAdaptiveGroups(limit: 10000, filter: {date: $day, requestHost_in: $hosts}) {
    count
    sum { visits }
    avg { sampleInterval }
    dimensions { date requestHost requestPath refererHost refererPath countryName deviceType userAgentBrowser userAgentOS bot }
  }
} } }"""


class AnalyticsError(Exception):
    """A problem reported by the Cloudflare GraphQL endpoint or an unexpected response shape."""


def default_post(url: str, body: bytes, headers: dict, timeout: float = 60.0) -> bytes:
    """POST *body* to *url* with *headers* and return the response body as bytes.

    Let urllib errors propagate so callers can catch them directly.
    """
    req = urllib.request.Request(url, data=body, method="POST", headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _post_json(url: str, body: dict, headers: dict, post=default_post, timeout: float = 60.0) -> dict:
    """Serialize *body* to JSON bytes and send via *post*, then parse the response JSON."""
    resp_bytes = post(url, json.dumps(body).encode("utf-8"), headers, timeout=timeout)
    return json.loads(resp_bytes)


def fetch_day(day: date, *, token: str, account: str, post=default_post) -> list[dict]:
    """Fetch analytics rows for one UTC day.

    Raises AnalyticsError on GraphQL errors, missing data shape, or when the result
    may have been truncated (PAGE+ rows returned). Returns a list of flat dicts,
    each with dimension keys plus ``page_views``, ``visits`` and ``sample_interval``.
    """
    body = {
        "query": QUERY,
        "variables": {"account": account, "day": day.isoformat(), "hosts": list(HOSTS)},
    }
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    result = _post_json(GRAPHQL_URL, body, headers, post)

    if isinstance(result.get("errors"), list) and len(result["errors"]) > 0:
        raise AnalyticsError(result["errors"][0].get("message", str(result["errors"])))

    accounts = (result.get("data") or {}).get("viewer", {}).get("accounts")
    if not accounts:
        raise AnalyticsError("No account found for the given tag")
    groups = accounts[0].get("rumPageloadEventsAdaptiveGroups")
    if groups is None:
        raise AnalyticsError("Missing rumPageloadEventsAdaptiveGroups in response")

    if len(groups) >= PAGE:
        raise AnalyticsError(f"Response has {len(groups)} rows — possibly truncated")

    rows = []
    for g in groups:
        dims = g.get("dimensions") or {}
        row = {k: v for k, v in dims.items()}
        row["page_views"] = g.get("count", 0)
        row["visits"] = (g.get("sum") or {}).get("visits", 0)
        row["sample_interval"] = (g.get("avg") or {}).get("sampleInterval", 1)
        rows.append(row)

    # Deterministic order independent of API response ordering.
    rows.sort(key=lambda r: json.dumps(r, sort_keys=True))
    return rows


def payload(day: date, rows: list[dict]) -> bytes:
    """Serialize *rows* for a given day into the canonical stored format.

    The day is included in the contents so two empty days never collide as "unchanged".
    Returns UTF-8 bytes ending with LF.
    """
    obj = {"day": day.isoformat(), "hosts": list(HOSTS), "rows": rows}
    return json.dumps(obj, indent=1, sort_keys=True, ensure_ascii=False).encode("utf-8") + b"\n"


def days_to_fetch(state: dict, today: date) -> list[date]:
    """Return each day from the day after the last stored one through yesterday."""
    yesterday = today - timedelta(days=1)
    last_str = state.get(STATE_KEY)
    if last_str is None:
        return [yesterday]
    try:
        last = date.fromisoformat(last_str)
    except (ValueError, TypeError):
        return [yesterday]
    days = []
    current = last + timedelta(days=1)
    while current <= yesterday:
        days.append(current)
        current += timedelta(days=1)
    return days


def _store_day(archive: Archive, day: date, rows: list[dict], now: datetime | None) -> StoreResult:
    return archive.store_bytes(
        SOURCE, DATASET, payload(day, rows), url=GRAPHQL_URL, retrieved_at=now or utc_now(), ext=".json",
        kind="fetched", extra={"day": day.isoformat(), "sampled": any(r["sample_interval"] != 1 for r in rows)},
    )


def export(archive: Archive, state: dict, today: date, *, token: str | None = None,
           account: str | None = None, post=default_post, now: datetime | None = None) -> dict:
    """Fetch and archive every finished day not yet stored.

    Returns ``result`` ("ok", "off" without a token, or "failed" with ``error``), the ``days``
    done and how many were ``stored``. On failure the state keeps the last day that worked, so
    the next call resumes there.
    """
    token = token or os.environ.get(TOKEN_ENV)
    account = account or os.environ.get(ACCOUNT_ENV)
    if not token or not account:
        return {"result": "off"}
    done: list[str] = []
    stored = 0
    for day in days_to_fetch(state, today):
        try:
            result = _store_day(archive, day, fetch_day(day, token=token, account=account, post=post), now)
        except (AnalyticsError, urllib.error.URLError, OSError, ValueError) as exc:
            return {"result": "failed", "error": f"{day}: {exc}", "days": done, "stored": stored}
        state[STATE_KEY] = day.isoformat()
        done.append(day.isoformat())
        stored += result.status == "stored"
    return {"result": "ok", "days": done, "stored": stored}


def export_day(archive: Archive, day: date, *, token: str | None = None,
               account: str | None = None, post=default_post, now: datetime | None = None) -> dict:
    """Fetch and archive one day without touching any state (a manual fill or a test). Raises on failure."""
    token = token or os.environ.get(TOKEN_ENV)
    account = account or os.environ.get(ACCOUNT_ENV)
    if not token or not account:
        raise AnalyticsError(f"{TOKEN_ENV} and {ACCOUNT_ENV} must be set")
    rows = fetch_day(day, token=token, account=account, post=post)
    result = _store_day(archive, day, rows, now)
    return {"result": "ok", "day": day.isoformat(), "rows": len(rows), "status": result.status}
