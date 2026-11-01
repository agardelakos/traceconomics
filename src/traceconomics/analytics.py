"""Copy daily counts from Cloudflare into the raw archive, one file per UTC day and feed.

Two feeds. Visits: Web Analytics rows (the beacon on our pages); Cloudflare keeps exact rows for
7 days, then only a sample, and lets the free plan query 184 days back. Downloads: requests for
the data files under `/downloads/`, from the zone's request data, which the beacon never sees
(a file download loads no page); every plan keeps 31 days. The archive keeps both for good. Each
day is one JSON file under `raw/cloudflare/<dataset>/`, with the day in its contents, so two
quiet days are two files.

Downloads are fetches, not people: one script can fetch a file many times, and most fetches come
from crawlers. Cloudflare's label for known bots (`verifiedBotCategory`) is stored with each row;
IP addresses and full user-agent strings are not.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from traceconomics.archive.store import Archive, StoreResult, utc_now

TOKEN_ENV = "TRACECONOMICS_ANALYTICS_TOKEN"
ACCOUNT_ENV = "CLOUDFLARE_ACCOUNT_ID"
ZONE_ENV = "CLOUDFLARE_ZONE_ID"
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

# HEAD requests and errors are kept (method and status are dimensions): what counts as a download
# is decided when the rows are read, not here.
DOWNLOADS_QUERY = """\
query ($zone: string!, $day: Date!, $hosts: [string!]) { viewer { zones(filter: {zoneTag: $zone}) {
  httpRequestsAdaptiveGroups(limit: 10000, filter: {date: $day, clientRequestHTTPHost_in: $hosts, clientRequestPath_like: "%/downloads/%"}) {
    count
    sum { edgeResponseBytes }
    avg { sampleInterval }
    dimensions { date clientRequestHTTPHost clientRequestPath clientRequestHTTPMethodName edgeResponseStatus clientCountryName clientDeviceType userAgentBrowser userAgentOS verifiedBotCategory requestSource }
  }
} } }"""


def _visit_counts(g: dict) -> dict:
    return {"page_views": g.get("count", 0), "visits": (g.get("sum") or {}).get("visits", 0)}


def _download_counts(g: dict) -> dict:
    return {"requests": g.get("count", 0), "bytes": (g.get("sum") or {}).get("edgeResponseBytes", 0)}


@dataclass(frozen=True)
class Feed:
    """One daily export: which dataset, which bookmark, and which GraphQL node under which scope."""

    name: str
    dataset: str
    state_key: str
    scope: str          # "accounts" or "zones"
    tag_env: str        # the environment variable holding the account or zone id
    node: str
    query: str
    counts: Callable[[dict], dict]  # group -> its count fields
    kept_days: int      # how long Cloudflare keeps exact rows: the time a failing export has


VISITS = Feed("visits", DATASET, STATE_KEY, "accounts", ACCOUNT_ENV, "rumPageloadEventsAdaptiveGroups",
              QUERY, _visit_counts, 7)
DOWNLOADS = Feed("downloads", "downloads", "downloads_through", "zones", ZONE_ENV, "httpRequestsAdaptiveGroups",
                 DOWNLOADS_QUERY, _download_counts, 31)
FEEDS = (VISITS, DOWNLOADS)


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


def fetch_day(day: date, *, token: str, account: str | None = None, zone: str | None = None,
              post=default_post, feed: Feed = VISITS) -> list[dict]:
    """Fetch one feed's rows for one UTC day.

    *account* is the tag for an account feed, *zone* for a zone feed. Raises AnalyticsError on
    GraphQL errors, missing data shape, or when the result may have been truncated (PAGE+ rows
    returned). Returns a list of flat dicts: the dimension keys, the feed's counts and
    ``sample_interval``.
    """
    tag_name, tag = ("account", account) if feed.scope == "accounts" else ("zone", zone)
    body = {
        "query": feed.query,
        "variables": {tag_name: tag, "day": day.isoformat(), "hosts": list(HOSTS)},
    }
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    result = _post_json(GRAPHQL_URL, body, headers, post)

    if isinstance(result.get("errors"), list) and len(result["errors"]) > 0:
        raise AnalyticsError(result["errors"][0].get("message", str(result["errors"])))

    scopes = (result.get("data") or {}).get("viewer", {}).get(feed.scope)
    if not scopes:
        raise AnalyticsError(f"No {tag_name} found for the given tag")
    groups = scopes[0].get(feed.node)
    if groups is None:
        raise AnalyticsError(f"Missing {feed.node} in response")

    if len(groups) >= PAGE:
        raise AnalyticsError(f"Response has {len(groups)} rows — possibly truncated")

    rows = []
    for g in groups:
        dims = g.get("dimensions") or {}
        row = {k: v for k, v in dims.items()}
        row.update(feed.counts(g))
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


def days_to_fetch(state: dict, today: date, key: str = STATE_KEY) -> list[date]:
    """Return each day from the day after the last stored one (bookmark *key*) through yesterday."""
    yesterday = today - timedelta(days=1)
    last_str = state.get(key)
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


def _store_day(archive: Archive, day: date, rows: list[dict], now: datetime | None, feed: Feed) -> StoreResult:
    return archive.store_bytes(
        SOURCE, feed.dataset, payload(day, rows), url=GRAPHQL_URL, retrieved_at=now or utc_now(), ext=".json",
        kind="fetched", extra={"day": day.isoformat(), "sampled": any(r["sample_interval"] != 1 for r in rows)},
    )


def _credentials(feed: Feed, token: str | None, account: str | None, zone: str | None):
    token = token or os.environ.get(TOKEN_ENV)
    if feed.scope == "accounts":
        return token, account or os.environ.get(ACCOUNT_ENV), None
    return token, None, zone or os.environ.get(ZONE_ENV)


def export(archive: Archive, state: dict, today: date, *, token: str | None = None,
           account: str | None = None, zone: str | None = None, post=default_post,
           now: datetime | None = None, feed: Feed = VISITS) -> dict:
    """Fetch and archive every finished day of *feed* not yet stored.

    Returns ``result`` ("ok", "off" without a token or the feed's account or zone id, or "failed"
    with ``error``), the ``days`` done and how many were ``stored``. On failure the state keeps
    the last day that worked, so the next call resumes there.
    """
    token, account, zone = _credentials(feed, token, account, zone)
    if not token or not (account or zone):
        return {"result": "off"}
    done: list[str] = []
    stored = 0
    for day in days_to_fetch(state, today, feed.state_key):
        try:
            rows = fetch_day(day, token=token, account=account, zone=zone, post=post, feed=feed)
            result = _store_day(archive, day, rows, now, feed)
        except (AnalyticsError, urllib.error.URLError, OSError, ValueError) as exc:
            return {"result": "failed", "error": f"{day}: {exc}", "days": done, "stored": stored}
        state[feed.state_key] = day.isoformat()
        done.append(day.isoformat())
        stored += result.status == "stored"
    return {"result": "ok", "days": done, "stored": stored}


def export_day(archive: Archive, day: date, *, token: str | None = None, account: str | None = None,
               zone: str | None = None, post=default_post, now: datetime | None = None,
               feed: Feed = VISITS) -> dict:
    """Fetch and archive one day without touching any state (a manual fill or a test). Raises on failure."""
    token, account, zone = _credentials(feed, token, account, zone)
    if not token or not (account or zone):
        raise AnalyticsError(f"{TOKEN_ENV} and {feed.tag_env} must be set")
    rows = fetch_day(day, token=token, account=account, zone=zone, post=post, feed=feed)
    result = _store_day(archive, day, rows, now, feed)
    return {"result": "ok", "day": day.isoformat(), "rows": len(rows), "status": result.status}
