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
    """When neither env var is set, export returns off and stores nothing."""
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
    """With an empty state dict, only yesterday is fetched and stored."""
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
    """State says 3 days ago; today should fetch the 2 intermediate days."""
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


def test_empty_days_stored_and_different_days_not_unchanged():
    """Two empty days each produce a stored file because the payload includes the date."""
    today = date(2026, 10, 28)
    yesterday = today - timedelta(days=1)

    # First run: yesterday is due, empty response -> stored.
    tmp_path = Path(tempfile.mkdtemp())
    post, _ = fake_post([_response([])])
    a = Archive(tmp_path)
    result1 = export(a, {}, today, token="tok", account="acc", post=post, now=_now(today))
    assert result1["result"] == "ok"
    assert result1["stored"] == 1

    # Second run with the same empty response for yesterday -> unchanged (same content).
    post2, _ = fake_post([_response([])])
    a2 = Archive(tmp_path)
    result2 = export(a2, {}, today, token="tok", account="acc", post=post2, now=_now(today))
    assert result2["result"] == "ok"
    assert result2["stored"] == 0

    # Two different empty days each get a separate stored file (different date in payload).
    tmp_path2 = Path(tempfile.mkdtemp())
    post3, _ = fake_post([_response([]), _response([])])
    a3 = Archive(tmp_path2)
    # State set so that both yesterday and day-2 need to be fetched.
    fresh_state = {"analytics_through": (today - timedelta(days=3)).isoformat()}
    result3 = export(a3, fresh_state, today, token="tok", account="acc", post=post3, now=_now(today))
    assert result3["result"] == "ok"
    # Both empty days are stored because their payloads differ (date string).
    assert result3["stored"] == 2


# -- 5. GraphQL errors list -> failed ------------------------------------- #


def test_graphql_errors_returns_failed():
    """A GraphQL error in the response returns 'failed' with state unchanged."""
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
    """A urllib error stops and returns 'failed'; state unchanged."""
    today = date(2026, 10, 28)

    tmp_path = Path(tempfile.mkdtemp())
    raise_count = [0]

    def raising_post(url, body, headers, timeout=60.0):
        raise_count[0] += 1
        raise urllib.error.URLError("network down")

    a = Archive(tmp_path)
    result = export(a, {}, today, token="tok", account="acc", post=raising_post, now=_now(today))

    assert result["result"] == "failed"
    assert raise_count[0] == 1


# -- 7. PAGE rows -> failed (truncated) ----------------------------------- #


def test_page_rows_returns_failed():
    """When the API returns PAGE or more rows, we treat it as possibly truncated."""
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
    """Groups returned in a different order yield identical payload, so the second is unchanged."""
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
    """A row with sampleInterval 10 produces manifest entry sampled=True."""
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


def test_export_day_stores_without_state():
    """export_day fetches one day and stores it; any state dict passed is ignored."""
    today = date(2026, 10, 28)

    tmp_path = Path(tempfile.mkdtemp())
    post, calls = fake_post([_response([_group()])])
    a = Archive(tmp_path)
    state = {"analytics_through": "2026-01-01"}  # stale value, should be ignored.

    result = export_day(a, today - timedelta(days=1), token="tok", account="acc", post=post)
    assert result["result"] == "ok"
    assert result["rows"] == 1
    assert result["status"] == "stored"

    # State must be unchanged.
    assert state == {"analytics_through": "2026-01-01"}
    # The API call was made for the right day.
    call_day = json.loads(calls[0]["body"])["variables"]["day"]
    assert call_day == (today - timedelta(days=1)).isoformat()
