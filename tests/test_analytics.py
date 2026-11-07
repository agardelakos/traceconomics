"""Cloudflare Web Analytics export: fetch, deduplicate and store daily visit counts."""

import json
import tempfile
import urllib.error
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from traceconomics.analytics import (
    AnalyticsError,
    Archive,
    days_to_fetch,
    export,
    export_day,
    fetch_day,
    payload,
)


def _group(host="traceconomics.com", path="/home", views=120, visits=80, interval=1, **dims):
    """Build one Cloudflare adaptive-group row for test fixtures."""
    return {
        "count": views,
        "sum": {"visits": visits},
        "avg": {"sampleInterval": interval},
        "dimensions": {
            "date": "2026-10-27T00:00:00Z",
            "requestHost": host,
            "requestPath": path,
            "refererHost": None,
            "refererPath": None,
            "countryName": "US",
            "deviceType": "Desktop",
            "userAgentBrowser": "Chrome",
            "userAgentOS": "Windows",
            "bot": False,
            **dims,
        },
    }


def _response(groups=None):
    """Build a full Cloudflare GraphQL response dict."""
    return {
        "data": {
            "viewer": {
                "accounts": [
                    {"rumPageloadEventsAdaptiveGroups": groups or []},
                ],
            },
        },
    }


def fake_post(canned=None, raise_on_call=None):
    """Return (post_fn, calls_list).

    *canned* is a list of response dicts returned in order for each call.
    *raise_on_call(index)* is called before each call; if it returns a truthy value
    that value (an Exception instance) is raised instead.
    """
    calls = []
    idx = [0]

    def post(url, body, headers, timeout=60.0):
        calls.append({"url": url, "body": body, "headers": dict(headers)})
        if raise_on_call and raise_on_call(idx[0]):
            raise raise_on_call(idx[0])
        resp = canned[idx[0]] if canned else {}
        idx[0] += 1
        return json.dumps(resp).encode("utf-8")

    return post, calls


def _now(d=date(2026, 10, 28)):
    """UTC datetime at midnight on day *d*."""
    return datetime(d.year, d.month, d.day, tzinfo=UTC)


# -- 1. off without token ------------------------------------------------- #


def test_off_without_token(monkeypatch):
    """PY-ANALYT-001: the analytics export is off without a token

    Given no analytics token or account id in the environment, and none passed
    When the visits export runs
    Then the result is "off"
    And the archive holds no dataset

    When neither env var is set, export returns off and stores nothing.
    """
    monkeypatch.delenv("TRACECONOMICS_ANALYTICS_TOKEN", raising=False)
    monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)
    tmp_path = Path(tempfile.mkdtemp()) / "off"
    a = Archive(tmp_path)
    result = export(a, {}, date(2026, 10, 28))
    assert result == {"result": "off"}
    # Nothing stored because no API call was made.
    a2 = Archive(tmp_path)
    assert a2.datasets() == []


# -- 2. first run with empty state ---------------------------------------- #


def test_first_run_empty_state_stores_yesterday():
    """PY-ANALYT-002: a first run with no bookmark stores yesterday only

    Given an empty job state and an API that returns one row
    When the visits export runs today
    Then the result is ok, for yesterday alone, with one file stored
    And the archive holds one snapshot of cloudflare/web-analytics
    And exactly one request went to Cloudflare's GraphQL address with the token as a bearer token
    And it asked for yesterday, the given account and both of the site's host names

    With an empty state dict, only yesterday is fetched and stored.
    """
    today = date(2026, 10, 28)
    yesterday = today - timedelta(days=1)

    resp = _response([_group()])
    post, calls = fake_post([resp])

    tmp_path = Path(tempfile.mkdtemp())
    a = Archive(tmp_path)
    result = export(a, {}, today, token="tok", account="acc", post=post, now=_now(today))

    assert result["result"] == "ok"
    assert result["days"] == [yesterday.isoformat()]
    assert result["stored"] == 1
    assert a.datasets() == [("cloudflare", "web-analytics")]
    snapshot = a.snapshots("cloudflare", "web-analytics")
    assert len(snapshot) == 1

    # The call was made with correct parameters.
    assert len(calls) == 1
    call = calls[0]
    assert call["url"] == "https://api.cloudflare.com/client/v4/graphql"
    assert call["headers"]["Authorization"] == "Bearer tok"
    variables = json.loads(call["body"])["variables"]
    assert variables["day"] == yesterday.isoformat()
    assert variables["account"] == "acc"
    assert variables["hosts"] == ["traceconomics.com", "www.traceconomics.com"]


# -- 3. catch-up: state says 3 days ago ----------------------------------- #


def test_catch_up_fetches_missing_days_in_order():
    """PY-ANALYT-003: a catch-up fetches the missing days in order

    Given a bookmark three days ago
    When the visits export runs today
    Then the result is ok for the two days since the bookmark, oldest first, with two files stored
    And the bookmark moves to yesterday
    And the requests asked for those two days in that order

    State says 3 days ago; today should fetch the 2 intermediate days.
    """
    today = date(2026, 10, 28)
    state = {"analytics_through": (today - timedelta(days=3)).isoformat()}

    day_a = today - timedelta(days=2)
    day_b = today - timedelta(days=1)
    post, calls = fake_post([_response([_group()]), _response([_group(host="www.traceconomics.com")])])

    tmp_path = Path(tempfile.mkdtemp())
    a = Archive(tmp_path)
    result = export(a, state, today, token="tok", account="acc", post=post, now=_now(today))

    assert result["result"] == "ok"
    assert result["days"] == [day_a.isoformat(), day_b.isoformat()]
    assert result["stored"] == 2
    # State updated to last done day.
    assert state["analytics_through"] == day_b.isoformat()
    body_days = [json.loads(c["body"])["variables"]["day"] for c in calls]
    assert body_days == [day_a.isoformat(), day_b.isoformat()]


# -- 4. empty days stored; different empty days don't collide -------------- #


def test_an_empty_day_is_stored_once():
    """PY-ANALYT-004: an empty day is stored once

    Given an API that returns no rows
    When the visits export runs today with no bookmark
    And it runs again into the same archive with no bookmark and the same empty answer
    Then the first run stores one file, for yesterday
    And the second run stores nothing new

    The second run is the same day with the same (empty) content, so the archive's dedup by
    content hash keeps the first file.
    """
    today = date(2026, 10, 28)

    tmp_path = Path(tempfile.mkdtemp())
    post, _ = fake_post([_response([])])
    result1 = export(Archive(tmp_path), {}, today, token="tok", account="acc", post=post, now=_now(today))
    assert result1["result"] == "ok"
    assert result1["days"] == ["2026-10-27"]
    assert result1["stored"] == 1

    post2, _ = fake_post([_response([])])
    result2 = export(Archive(tmp_path), {}, today, token="tok", account="acc", post=post2, now=_now(today))
    assert result2["result"] == "ok"
    assert result2["stored"] == 0


def test_two_empty_days_are_stored_apart():
    """PY-ANALYT-016: two empty days are stored apart

    Given an API that returns no rows, and a bookmark three days before today
    When the visits export runs today
    Then two days are fetched, and each is stored as its own file

    Two empty days each produce a stored file because the payload includes the date: if it
    didn't, dedup would keep only the first and the second day would look already stored.
    """
    today = date(2026, 10, 28)

    tmp_path = Path(tempfile.mkdtemp())
    post, _ = fake_post([_response([]), _response([])])
    state = {"analytics_through": (today - timedelta(days=3)).isoformat()}
    result = export(Archive(tmp_path), state, today, token="tok", account="acc", post=post, now=_now(today))
    assert result["result"] == "ok"
    assert result["days"] == ["2026-10-26", "2026-10-27"]
    assert result["stored"] == 2


# -- 5. GraphQL errors list -> failed ------------------------------------- #


def test_graphql_errors_returns_failed():
    """PY-ANALYT-005: a GraphQL error fails the export without moving the bookmark

    Given an API whose answer carries a GraphQL error
    When the visits export runs today with no bookmark
    Then the result is "failed" and the error names yesterday's date
    And no bookmark is set
    And the archive holds no dataset

    A GraphQL error in the response returns 'failed' with state unchanged.
    """
    today = date(2026, 10, 28)
    yesterday = today - timedelta(days=1)
    err_resp = {"errors": [{"message": "Access denied", "extensions": {}}]}

    tmp_path = Path(tempfile.mkdtemp())
    post, _ = fake_post([err_resp])
    a = Archive(tmp_path)
    state = {}
    result = export(a, state, today, token="tok", account="acc", post=post, now=_now(today))

    assert result["result"] == "failed"
    assert "2026-10-27: " in result["error"]
    # State untouched — nothing was stored.
    assert state.get("analytics_through") is None
    assert a.datasets() == []


# -- 6. fake post raising URLError ---------------------------------------- #


def test_url_error_returns_failed():
    """PY-ANALYT-006: a network error fails the export after one request, keeping the bookmark

    Given a bookmark three days before today, and an API that cannot be reached
    When the visits export runs today
    Then the result is "failed"
    And exactly one request was tried
    And the bookmark is where it was
    And the archive holds no dataset

    A urllib error stops the run at the first day; the next run resumes from the same bookmark.
    """
    today = date(2026, 10, 28)

    tmp_path = Path(tempfile.mkdtemp())
    raise_count = [0]

    def raising_post(url, body, headers, timeout=60.0):
        raise_count[0] += 1
        raise urllib.error.URLError("network down")

    a = Archive(tmp_path)
    state = {"analytics_through": "2026-10-25"}
    result = export(a, state, today, token="tok", account="acc", post=raising_post, now=_now(today))

    assert result["result"] == "failed"
    assert raise_count[0] == 1
    assert state == {"analytics_through": "2026-10-25"}
    assert a.datasets() == []


# -- 7. PAGE rows -> failed (truncated) ----------------------------------- #


def test_page_rows_returns_failed():
    """PY-ANALYT-007: a full page of rows fails the export as possibly truncated

    Given an API that returns exactly a page's limit of rows
    When the visits export runs today
    Then the result is "failed"
    And the error says "possibly truncated"

    When the API returns PAGE or more rows, we treat it as possibly truncated.
    """
    from traceconomics.analytics import PAGE

    today = date(2026, 10, 28)
    too_many = [_group() for _ in range(PAGE)]

    tmp_path = Path(tempfile.mkdtemp())
    post, _ = fake_post([_response(too_many)])
    a = Archive(tmp_path)
    result = export(a, {}, today, token="tok", account="acc", post=post, now=_now(today))

    assert result["result"] == "failed"
    assert "possibly truncated" in result["error"]


# -- 8. deterministic order: different input groups -> same stored bytes --- #


def test_different_group_order_produces_same_stored_bytes():
    """PY-ANALYT-008: the same rows in another order are not stored again

    Given a day's rows already stored
    When the visits export runs again and the API returns the same rows in another order
    Then the result is ok with nothing stored

    Groups returned in a different order yield identical payload, so the second is unchanged.
    """
    today = date(2026, 10, 28)

    rows_a = [_group(host="a.com"), _group(host="b.com")]
    rows_b = [_group(host="b.com"), _group(host="a.com")]

    # First call: store with groups in order A.
    tmp_path = Path(tempfile.mkdtemp())
    post1, _ = fake_post([_response(rows_a)])
    a = Archive(tmp_path)
    result1 = export(a, {}, today, token="tok", account="acc", post=post1, now=_now(today))
    assert result1["stored"] == 1

    # Second call with groups shuffled: same rows but different order -> should be unchanged.
    post2, _ = fake_post([_response(rows_b)])
    a2 = Archive(tmp_path)
    result2 = export(a2, {}, today, token="tok", account="acc", post=post2, now=_now(today))
    assert result2["result"] == "ok"
    assert result2["stored"] == 0


# -- 9. sampled row: sampleInterval != 1 ---------------------------------- #


def test_sampled_flag_in_manifest():
    """PY-ANALYT-009: a sampled row marks the stored day as sampled

    Given an API that returns one unsampled row and one with a sample interval of 10
    When the visits export runs today
    Then one file is stored
    And its manifest says sampled is true

    A row with sampleInterval 10 produces manifest entry sampled=True.
    """
    today = date(2026, 10, 28)
    rows_sampled = [_group(interval=1), _group(interval=10)]

    tmp_path = Path(tempfile.mkdtemp())
    post, _ = fake_post([_response(rows_sampled)])
    a = Archive(tmp_path)
    result = export(a, {}, today, token="tok", account="acc", post=post, now=_now(today))

    assert result["stored"] == 1
    # Read the manifest from the stored path.
    snaps = a.snapshots("cloudflare", "web-analytics")
    assert len(snaps) == 1
    rec = snaps[0]
    record = a.manifest(rec)
    assert record["sampled"] is True


# -- 10. export_day stores and leaves state untouched ---------------------- #


def test_export_day_stores_the_chosen_day():
    """PY-ANALYT-010: exporting one chosen day stores it

    Given an API that returns one row
    When yesterday alone is exported
    Then the result is ok, with one row and status "stored"
    And the request asked for yesterday
    And the archive holds the visits dataset

    export_day takes no job state, so it can't move a bookmark: there is nothing to check there.
    """
    today = date(2026, 10, 28)

    tmp_path = Path(tempfile.mkdtemp())
    post, calls = fake_post([_response([_group()])])
    a = Archive(tmp_path)

    result = export_day(a, today - timedelta(days=1), token="tok", account="acc", post=post)
    assert result["result"] == "ok"
    assert result["rows"] == 1
    assert result["status"] == "stored"

    call_day = json.loads(calls[0]["body"])["variables"]["day"]
    assert call_day == (today - timedelta(days=1)).isoformat()
    assert len(a.datasets()) == 1


# -- downloads feed ------------------------------------------------------- #

from traceconomics.analytics import DOWNLOADS  # noqa: E402


def _download_group(path="/data/v1/gr/m1/latest/downloads/x/m1_index.csv", requests=3, bytes_=4096,
                    bot="AI Crawler", interval=1):
    return {
        "count": requests,
        "sum": {"edgeResponseBytes": bytes_},
        "avg": {"sampleInterval": interval},
        "dimensions": {
            "date": "2026-10-27",
            "clientRequestHTTPHost": "traceconomics.com",
            "clientRequestPath": path,
            "clientRequestHTTPMethodName": "GET",
            "edgeResponseStatus": 200,
            "clientCountryName": "NO",
            "clientDeviceType": "desktop",
            "userAgentBrowser": "Other",
            "userAgentOS": "Other",
            "verifiedBotCategory": bot,
            "requestSource": "eyeball",
        },
    }


def _zone_response(groups=None):
    return {"data": {"viewer": {"zones": [{"httpRequestsAdaptiveGroups": groups or []}]}}}


def test_downloads_off_without_zone(monkeypatch):
    """PY-ANALYT-011: the downloads export is off without a zone id

    Given a token and an account id but no zone id in the environment or passed
    When the downloads export runs
    Then the result is "off"

    The token alone isn't enough: the zone feed needs the zone id too.
    """
    monkeypatch.delenv("CLOUDFLARE_ZONE_ID", raising=False)
    a = Archive(Path(tempfile.mkdtemp()))
    assert export(a, {}, date(2026, 10, 28), token="tok", account="acc", feed=DOWNLOADS) == {"result": "off"}


def test_downloads_stored_in_their_own_dataset_with_their_own_bookmark():
    """PY-ANALYT-012: downloads are stored in their own dataset with their own bookmark

    Given a visits bookmark a week ago, no downloads bookmark, and a zone answer with two data-file rows (one from a bot, one not)
    When the downloads export runs today
    Then the result is ok for yesterday with one file stored
    And the downloads bookmark is set to yesterday while the visits bookmark is untouched
    And the archive holds only cloudflare/downloads
    And the request asked for the zone, yesterday and both host names
    And its query reads the zone's request groups for paths under /downloads/
    And it asks for no IP address and no full user-agent string
    And the stored rows keep their request counts (1 and 3), byte counts and bot categories (none and "AI Crawler")
    """
    today = date(2026, 10, 28)
    post, calls = fake_post([_zone_response([_download_group(), _download_group(bot="", requests=1)])])
    a = Archive(Path(tempfile.mkdtemp()))
    state = {"analytics_through": "2026-10-20"}
    result = export(a, state, today, token="tok", zone="zone1", post=post, now=_now(today), feed=DOWNLOADS)

    assert result == {"result": "ok", "days": ["2026-10-27"], "stored": 1}
    assert state == {"analytics_through": "2026-10-20", "downloads_through": "2026-10-27"}
    assert a.datasets() == [("cloudflare", "downloads")]
    body = json.loads(calls[0]["body"])
    assert body["variables"] == {"zone": "zone1", "day": "2026-10-27", "hosts": ["traceconomics.com", "www.traceconomics.com"]}
    assert "httpRequestsAdaptiveGroups" in body["query"] and '"%/downloads/%"' in body["query"]
    # No IP address or full user-agent string is asked for.
    assert "clientIP" not in body["query"] and "userAgent " not in body["query"]

    snap = a.snapshots("cloudflare", "downloads")[0]
    rows = json.loads((a.root / snap["path"]).read_bytes())["rows"]
    assert {r["requests"] for r in rows} == {1, 3} and all(r["bytes"] == 4096 for r in rows)
    assert {r["verifiedBotCategory"] for r in rows} == {"", "AI Crawler"}


def test_downloads_rows_have_request_and_byte_counts():
    """PY-ANALYT-013: a downloads row has request and byte counts, not page views

    Given a zone answer with one row of 5 requests, 100 bytes and a sample interval of 2
    When the day is fetched for the downloads feed
    Then there is one row with 5 requests, 100 bytes and sample interval 2
    And it has no page-view count
    """
    post, _ = fake_post([_zone_response([_download_group(requests=5, bytes_=100, interval=2)])])
    rows = fetch_day(date(2026, 10, 27), token="tok", zone="z", post=post, feed=DOWNLOADS)
    assert len(rows) == 1
    assert rows[0]["requests"] == 5 and rows[0]["bytes"] == 100 and rows[0]["sample_interval"] == 2
    assert "page_views" not in rows[0]


def test_downloads_missing_zone_in_response_fails():
    """PY-ANALYT-014: a downloads answer without the zone fails

    Given an API answer with no zone in it
    When a day is fetched for the downloads feed
    Then an AnalyticsError naming the zone is raised
    """
    post, _ = fake_post([{"data": {"viewer": {"zones": []}}}])
    with pytest.raises(AnalyticsError, match="zone"):
        fetch_day(date(2026, 10, 27), token="tok", zone="z", post=post, feed=DOWNLOADS)


def test_export_day_downloads_needs_zone(monkeypatch):
    """PY-ANALYT-015: exporting one day of downloads needs the zone id

    Given no zone id in the environment or passed
    When one day of downloads is exported
    Then an AnalyticsError naming CLOUDFLARE_ZONE_ID is raised
    """
    monkeypatch.delenv("CLOUDFLARE_ZONE_ID", raising=False)
    with pytest.raises(AnalyticsError, match="CLOUDFLARE_ZONE_ID"):
        export_day(Archive(Path(tempfile.mkdtemp())), date(2026, 10, 27), token="tok", feed=DOWNLOADS)
