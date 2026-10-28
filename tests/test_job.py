from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from traceconomics import job
from traceconomics.archive.store import Archive
from traceconomics.config import Config
from traceconomics.sources import base, eurostat

ATH = ZoneInfo("Europe/Athens")
FIX = Path(__file__).parent / "fixtures"


def cfg(tmp_path, **kw):
    return Config(archive_dir=tmp_path / "archive", user_agent="test", **kw)


def at(y, m, d, hh, mm=0):
    return datetime(y, m, d, hh, mm, tzinfo=ATH)


def state_with(dates, last):
    return {"release_dates": {"elstat-cpi": [d.isoformat() for d in dates]}, "last_good_run": last}


# -- when a run is due ------------------------------------------------------

def test_first_run_is_due(tmp_path):
    assert job.check_due({}, cfg(tmp_path), at(2026, 10, 18, 9)).due


def test_release_day_due_only_after_run_time(tmp_path):
    s = state_with([date(2026, 11, 10)], "2026-10-18")
    c = cfg(tmp_path)
    assert not job.check_due(s, c, at(2026, 11, 10, 12, 59)).due
    d = job.check_due(s, c, at(2026, 11, 10, 13, 0))
    assert d.due and d.release_days == [date(2026, 11, 10)] and d.missed == []


def test_missed_release_day_is_caught_up_and_reported(tmp_path):
    s = state_with([date(2026, 11, 10)], "2026-10-18")
    d = job.check_due(s, cfg(tmp_path), at(2026, 11, 12, 8))
    assert d.due and d.missed == [date(2026, 11, 10)]


def test_not_due_without_release(tmp_path):
    s = state_with([date(2026, 11, 10)], "2026-11-10")
    assert not job.check_due(s, cfg(tmp_path), at(2026, 11, 11, 14)).due


def test_extra_dates_count(tmp_path):
    s = state_with([], "2026-10-18")
    c = cfg(tmp_path, extra_release_dates=(date(2026, 10, 20),))
    assert job.check_due(s, c, at(2026, 10, 20, 14)).due


# -- whole runs against fake publishers -------------------------------------

class FakeHttp:
    """Serves fixtures instead of the network and records what was asked for."""

    def __init__(self, files):
        self.files = files
        self.requested = []

    def download(self, url, dest):
        self.requested.append(url)
        for key, content in self.files.items():
            if key in url:
                dest.write_bytes(content)
                return base.Response(url=url, status=200, headers={}, retrieved_at=base.utc_now())
        raise base.FetchError(f"{url}: 404")

    def get_bytes(self, url, tmp):
        self.download(url, tmp)
        data = tmp.read_bytes()
        tmp.unlink()
        return None, data


def fake_files():
    page = (FIX / "elstat_cpi_page.html").read_bytes()
    return {
        "/en/calendar": (FIX / "elstat_calendar.html").read_bytes(),
        "DKT87": page,
        "DKT90": page,
        "SFA05": page,
        "documentID=": b"xlsx bytes",
        "puf_en.jsp": (FIX / "elstat_puf_catalogue.html").read_bytes(),
        "eventsJson": (FIX / "eurostat_calendar.json").read_bytes(),
        "/dataflow/": (FIX / "eurostat_dataflow_prc_hicp_minr.xml").read_bytes(),
        "format=TSV": b"tsv.gz bytes",
        "prc_hicp_esms": b"<html><body><p>metadata</p></body></html>",
        "copyright-notice": b"<html><body><p>reuse allowed</p></body></html>",
        "pneumatika": b"<html><body><p>reuse allowed</p></body></html>",
        "Copyright_Reuse_Policy": b"%PDF terms",
    }


@pytest.fixture
def fake_http(monkeypatch):
    http = FakeHttp(fake_files())
    monkeypatch.setattr(job, "HttpClient", lambda *a, **k: http)
    return http


def outbox(c):
    return sorted((c.archive_dir / "outbox").iterdir(), key=lambda p: p.stat().st_mtime_ns)


def test_full_run_then_second_run_stores_nothing(tmp_path, fake_http):
    c = cfg(tmp_path)
    first = job.run(c, now=at(2026, 10, 18, 14))
    assert first["result"] == "ok", first
    assert first["stored"] > 10
    assert "Files to back up" in outbox(c)[0].read_text(encoding="utf-8")

    second = job.run(c, now=at(2026, 10, 18, 15), force=True)
    assert second["stored"] == 0 and second["result"] == "ok"
    # Eurostat's "last data update" didn't change, so the big files weren't downloaded again.
    tsv = [u for u in fake_http.requested if "format=TSV" in u]
    assert len(tsv) == len(eurostat.LIVE) + len(eurostat.FROZEN)


def test_changed_terms_raise_an_alert(tmp_path, fake_http):
    c = cfg(tmp_path)
    job.run(c, now=at(2026, 10, 18, 14))
    fake_http.files["copyright-notice"] = b"<html><body><p>new terms</p></body></html>"
    job.run(c, now=at(2026, 10, 18, 15), force=True)
    last = outbox(c)[-1]
    assert "alert" in last.name
    assert "Reuse terms changed" in last.read_text(encoding="utf-8")


def test_new_puf_year_raises_an_alert(tmp_path, fake_http):
    c = cfg(tmp_path)
    job.run(c, now=at(2026, 10, 18, 14))
    page = fake_http.files["puf_en.jsp"].replace(b"2008 - 2024", b"2008 - 2025")
    fake_http.files["puf_en.jsp"] = page
    job.run(c, now=at(2026, 10, 18, 15), force=True)
    assert "now: Household Budget Survey (HBS) | 2008 - 2025" in outbox(c)[-1].read_text(encoding="utf-8")


def test_failures_keep_the_run_due(tmp_path, fake_http):
    c = cfg(tmp_path)
    del fake_http.files["puf_en.jsp"]
    r = job.run(c, now=at(2026, 10, 18, 14))
    assert r["result"] == "failures"
    assert "last_good_run" not in job.load_state(c.archive_dir)


def test_dry_run_stores_nothing(tmp_path, fake_http):
    c = cfg(tmp_path)
    r = job.run(c, dry_run=True, now=at(2026, 10, 18, 14))
    assert r["result"] == "dry-run" and r["planned"]
    assert not fake_http.requested
    assert not (c.archive_dir / "raw" / "index.jsonl").exists()


def test_morning_run_doesnt_cover_that_days_release(tmp_path, fake_http):
    c = cfg(tmp_path)
    job.run(c, now=at(2026, 10, 18, 9), force=True)
    assert job.load_state(c.archive_dir)["last_good_run"] == "2026-10-17"


def test_backup_mark(tmp_path, fake_http):
    c = cfg(tmp_path)
    job.run(c, now=at(2026, 10, 18, 14))
    job.mark_backup_done(c)
    mark = job.load_state(c.archive_dir)["backup_mark"]
    assert Archive(c.archive_dir).stored_since(mark) == []


def test_heartbeat_backup_and_release_follow_a_run_with_new_data(tmp_path, fake_http, monkeypatch):
    from traceconomics import release
    from traceconomics.config import ReleaseConfig

    beats, builds = [], []
    monkeypatch.setattr(job.heartbeat, "send", lambda record: beats.append(record["result"]) or "sent")
    monkeypatch.setattr(job.backup, "sync", lambda root: {"result": "ok", "sent": 1})
    monkeypatch.setattr(release, "build", lambda config, reason: builds.append(reason) or {"id": "R1"})
    on = ReleaseConfig(enabled=True, releases_dir=tmp_path / "rel", site_dir=tmp_path / "site")

    first = job.run(cfg(tmp_path, release=on), now=at(2026, 10, 18, 14))
    assert first["heartbeat"] == "sent" and first["backup"]["result"] == "ok" and first["release"] == "R1"
    assert "eurostat/prc_hicp_minr" in builds[0]
    # Nothing new: no release; a day without a release still sends its heartbeat.
    again = job.run(cfg(tmp_path, release=on), now=at(2026, 10, 18, 15), force=True)
    assert "release" not in again and "backup" not in again
    quiet = job.run(cfg(tmp_path, release=on), now=at(2026, 10, 19, 14))
    assert quiet["result"] == "not-due" and quiet["heartbeat"] == "sent"
    assert len(builds) == 1 and beats == ["ok", "ok", "not-due"]


def test_release_is_off_by_default(tmp_path, fake_http, monkeypatch):
    from traceconomics import release

    monkeypatch.setattr(release, "build", lambda *a, **k: pytest.fail("no release on a machine without [release]"))
    assert "release" not in job.run(cfg(tmp_path), now=at(2026, 10, 18, 14))


# -- visit counts (exported every day, due or not) ---------------------------

def _not_due_state(tmp_path):
    root = tmp_path / "archive"
    (root / "state").mkdir(parents=True)
    job.save_state(root, state_with([date(2026, 11, 10)], "2026-11-10"))


def test_a_quiet_day_still_exports_visit_counts_and_backs_them_up(tmp_path, monkeypatch):
    _not_due_state(tmp_path)
    seen, synced = [], []

    def fake_export(archive, state, today):
        seen.append(today)
        archive.store_bytes("cloudflare", "web-analytics", b'{"day": "2026-11-11"}\n', url=None,
                            retrieved_at=datetime(2026, 11, 12, 11, tzinfo=ZoneInfo("UTC")), ext=".json",
                            extra={"day": "2026-11-11"})
        state["analytics_through"] = "2026-11-11"
        return {"result": "ok", "days": ["2026-11-11"], "stored": 1}

    monkeypatch.setattr(job.analytics, "export", fake_export)
    monkeypatch.setattr(job.backup, "sync", lambda root: synced.append(root) or {"result": "ok", "sent": 1})
    monkeypatch.setattr(job.heartbeat, "send", lambda record: "sent")
    rec = job.run(cfg(tmp_path), now=at(2026, 11, 12, 13))
    assert rec["result"] == "not-due" and rec["analytics"]["stored"] == 1 and rec["backup"]["result"] == "ok"
    assert seen == [date(2026, 11, 12)] and len(synced) == 1
    assert job.load_state(tmp_path / "archive")["analytics_through"] == "2026-11-11"


def test_the_bookmark_is_rebuilt_from_the_archive(tmp_path, monkeypatch):
    archive = Archive(tmp_path / "archive")
    # Stored last but not the latest day (a manual fill), and today's, not over yet: neither counts.
    for day, stored_hour in (("2026-11-09", 11), ("2026-11-05", 12), ("2026-11-12", 13)):
        archive.store_bytes("cloudflare", "web-analytics", f'{{"day": "{day}"}}\n'.encode(), url=None,
                            retrieved_at=datetime(2026, 11, 12, stored_hour, tzinfo=ZoneInfo("UTC")), ext=".json",
                            extra={"day": day})
    seen = []
    monkeypatch.setattr(job.analytics, "export", lambda archive, state, today: seen.append(dict(state)) or {"result": "off"})
    job.export_analytics(cfg(tmp_path), archive, {}, at(2026, 11, 12, 13))
    assert seen[0]["analytics_through"] == "2026-11-09"


@pytest.mark.parametrize("through, alerts", [("2026-11-10", 0), ("2026-11-07", 1), (None, 1)])
def test_a_failing_export_alerts_only_when_days_are_running_out(tmp_path, monkeypatch, through, alerts):
    sent = []
    monkeypatch.setattr(job, "notify", lambda config, subject, body: sent.append(subject) or "outbox")
    monkeypatch.setattr(job.analytics, "export", lambda archive, state, today: {"result": "failed", "error": "401"})
    state = {} if through is None else {"analytics_through": through}
    job.export_analytics(cfg(tmp_path), Archive(tmp_path / "archive"), state, at(2026, 11, 12, 13))
    assert len(sent) == alerts and all(s.startswith("ALERT: analytics export") for s in sent)
