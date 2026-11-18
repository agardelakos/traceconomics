from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from traceconomics import job
from traceconomics.archive.store import Archive, stamp
from traceconomics.config import Config
from traceconomics.sources import base, ec_empl, eurostat

pytestmark = pytest.mark.integration

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
    """PY-JOB-001: the first run is always due

    Given no job state (no good run yet)
    When the scheduled job checks whether a run is due, in the morning before the run time
    Then a run is due
    """
    assert job.check_due({}, cfg(tmp_path), at(2026, 10, 18, 9)).due


@pytest.mark.parametrize("hh, mm, due", [(12, 59, False), (13, 0, True)], ids=["12:59", "13:00"])
def test_release_day_due_only_after_run_time(tmp_path, hh, mm, due):
    """PY-JOB-002: on a release day the run is due only from the run time

    Given a known release day after the last good run
    When the scheduled job checks that day, at 12:59 or at 13:00 Greek time
    Then at 12:59 no run is due
    And at 13:00 a run is due for that release day, with no missed days
    """
    s = state_with([date(2026, 11, 10)], "2026-10-18")
    d = job.check_due(s, cfg(tmp_path), at(2026, 11, 10, hh, mm))
    assert d.due is due
    if due:
        assert d.release_days == [date(2026, 11, 10)] and d.missed == []


def test_missed_release_day_is_caught_up_and_reported(tmp_path):
    """PY-JOB-003: a missed release day is caught up and reported as missed

    Given a release day that passed with no run since the last good run
    When the scheduled job checks two days later, before the run time
    And the run's report is written
    Then a run is due
    And that release day is listed as missed
    And the report has a MISSED line naming that day
    """
    s = state_with([date(2026, 11, 10)], "2026-10-18")
    c = cfg(tmp_path)
    now = at(2026, 11, 12, 8)
    d = job.check_due(s, c, now)
    assert d.due and d.missed == [date(2026, 11, 10)]
    ctx = SimpleNamespace(alerts=[], failures=[])
    report = job.render_report(c, now, d, False, [], [], ctx, [])
    assert "MISSED (no run on the day): 2026-11-10" in report.splitlines()


def test_not_due_without_release(tmp_path):
    """PY-JOB-004: no run is due without a release since the last good run

    Given a last good run on the latest known release day
    When the scheduled job checks the next day after the run time
    Then no run is due
    """
    s = state_with([date(2026, 11, 10)], "2026-11-10")
    assert not job.check_due(s, cfg(tmp_path), at(2026, 11, 11, 14)).due


def test_extra_dates_count(tmp_path):
    """PY-JOB-005: extra release dates in the configuration make a run due

    Given no known release dates but an extra release date in the configuration
    When the scheduled job checks on that date after the run time
    Then a run is due
    """
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
        "legal-notice": b"<html><body><p>reuse allowed</p></body></html>",
        "annual-statistical-reports-natural-persons": (
            FIX / "aade_annual_reports_natural_persons_en.html"
        ).read_bytes(),
        "/sites/default/files/": b"xlsx bytes",
        "terms-use-iaprs-website": b"<html><body><p>use allowed if accurately reproduced</p></body></html>",
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
    """PY-JOB-006: a full run stores the sources, and a second run stores nothing new

    Given fake publishers serving trimmed real pages and files
    When the scheduled job runs for the first time
    And a forced second run follows the same day
    Then the first run is ok with more than 10 files stored
    And its report in the outbox lists the files to back up
    And the second run is ok with nothing stored
    And Eurostat's and DG EMPL's data files were downloaded only once each, since their last update didn't change
    """
    c = cfg(tmp_path)
    first = job.run(c, now=at(2026, 10, 18, 14))
    assert first["result"] == "ok", first
    assert first["stored"] > 10
    assert "Files to back up" in outbox(c)[0].read_text(encoding="utf-8")

    second = job.run(c, now=at(2026, 10, 18, 15), force=True)
    assert second["stored"] == 0 and second["result"] == "ok"
    # Eurostat's "last data update" didn't change, so the big files weren't downloaded again.
    tsv = [u for u in fake_http.requested if "format=TSV" in u]
    assert len(tsv) == len(eurostat.LIVE) + len(eurostat.FROZEN) + len(ec_empl.LIVE)


def test_the_daily_run_never_asks_aade(tmp_path, fake_http):
    """PY-JOB-021: the daily run never asks AADE, so its CDN's refusal can't stop a release

    Given fake publishers that would serve AADE's statistics page, workbooks and terms page
    When the scheduled job runs
    Then the run is ok
    And no address on www.aade.gr was requested
    """
    c = cfg(tmp_path)
    assert job.run(c, now=at(2026, 10, 18, 14))["result"] == "ok"
    assert fake_http.requested
    assert not [u for u in fake_http.requested if "aade.gr" in u]


def test_changed_terms_raise_an_alert(tmp_path, fake_http):
    """PY-JOB-007: changed reuse terms raise an alert

    Given a first run that stored a publisher's reuse terms page
    When the page changes and a forced run follows
    Then the latest outbox message is an alert
    And it says the reuse terms changed
    """
    c = cfg(tmp_path)
    job.run(c, now=at(2026, 10, 18, 14))
    fake_http.files["copyright-notice"] = b"<html><body><p>new terms</p></body></html>"
    job.run(c, now=at(2026, 10, 18, 15), force=True)
    last = outbox(c)[-1]
    assert "alert" in last.name
    assert "Reuse terms changed" in last.read_text(encoding="utf-8")


# -- a release day must bring its release ------------------------------------


CPI_ROW = b'contentDay">12/02/26</td> <td class="contentIndicator"><a href="https://www.statistics.gr/documents/20181/daeaf450'


def cpi_release_on_nov_10(fake_http):
    """ELSTAT's calendar (the saved page, changed in memory) with its CPI row moved to 2026-11-10."""
    page = fake_http.files["/en/calendar"]
    assert page.count(CPI_ROW) == 1
    fake_http.files["/en/calendar"] = page.replace(CPI_ROW, CPI_ROW.replace(b"12/02/26", b"10/11/26"))


def report_of(c):
    return outbox(c)[-1].read_text(encoding="utf-8")


LATE_CPI = "ELSTAT's CPI: release day 2026-11-10, but no new file by 14:00"


def test_a_release_day_without_its_files_alerts_and_stays_due(tmp_path, fake_http):
    """PY-JOB-023: a release day whose files haven't changed raises an alert and stays due

    Given a first run that archived ELSTAT's CPI documents
    And ELSTAT's CPI release day on 2026-11-10
    When the 13:00 run that day finds every CPI document unchanged (the release is late)
    Then the run is ok, and its report alerts that the CPI release day brought no new file
    And the next day after 13:00 a run is due, waiting for the late release
    """
    c = cfg(tmp_path)
    cpi_release_on_nov_10(fake_http)
    job.run(c, now=at(2026, 10, 18, 14))
    r = job.run(c, now=at(2026, 11, 10, 14))
    assert r["result"] == "ok" and r["reason"] == "release day"
    assert LATE_CPI in report_of(c) and outbox(c)[-1].name.find("alert") >= 0
    d = job.check_due(job.load_state(c.archive_dir), c, at(2026, 11, 11, 14))
    assert d.due and d.reason == "waiting for a late release" and date(2026, 11, 10) in d.release_days


def test_late_files_end_the_wait_and_every_document_is_read_again(tmp_path, fake_http):
    """PY-JOB-024: the late release arriving the next day ends the wait; every document is read again

    Given a CPI release day on 2026-11-10 that brought no new file
    When ELSTAT's documents change and the next day's run happens
    Then that run downloads every document on the CPI page again, old IDs included (ELSTAT updates some in place)
    And its report has no late-release alert
    And the CPI's confirmed release day is 2026-11-10, and no run is due the day after
    """
    c = cfg(tmp_path)
    cpi_release_on_nov_10(fake_http)
    job.run(c, now=at(2026, 10, 18, 14))
    job.run(c, now=at(2026, 11, 10, 14))
    fake_http.files["documentID="] = b"xlsx bytes, the October release"
    asked = len(fake_http.requested)
    r = job.run(c, now=at(2026, 11, 11, 14))
    docs = {u.split("documentID=")[1].split("&")[0] for u in fake_http.requested[asked:] if "documentID=" in u}
    assert {"114858", "114862", "585410", "588584", "591429", "594835"} <= docs
    assert r["reason"] == "waiting for a late release" and "ELSTAT's CPI" not in report_of(c)
    state = job.load_state(c.archive_dir)
    assert state["release_confirmed"]["elstat-cpi"] == "2026-11-10"
    assert "elstat-cpi" not in job.awaited(state, date(2026, 11, 12))


def test_a_release_on_time_is_confirmed_without_an_alert(tmp_path, fake_http):
    """PY-JOB-025: a release day whose files arrive in time is confirmed, with no alert about it

    Given a first run that archived ELSTAT's CPI documents
    When ELSTAT's documents change and the 13:00 run on the CPI release day 2026-11-10 happens
    Then its report has no late-release alert
    And the CPI's confirmed release day is 2026-11-10, and no run is due the next day
    """
    c = cfg(tmp_path)
    cpi_release_on_nov_10(fake_http)
    job.run(c, now=at(2026, 10, 18, 14))
    fake_http.files["documentID="] = b"xlsx bytes, the October release"
    job.run(c, now=at(2026, 11, 10, 14))
    assert "ELSTAT's CPI" not in report_of(c)
    state = job.load_state(c.archive_dir)
    assert state["release_confirmed"]["elstat-cpi"] == "2026-11-10"
    assert "elstat-cpi" not in job.awaited(state, date(2026, 11, 11))


def test_a_page_edit_is_not_the_release(tmp_path, fake_http):
    """PY-JOB-026: a changed publication page with unchanged documents doesn't count as the release

    Given a first run that archived ELSTAT's CPI page and documents
    When on the CPI release day a document's title changes on the page, but no document changes
    Then the new page is stored
    And the report still alerts that the CPI release day brought no new file
    """
    c = cfg(tmp_path)
    cpi_release_on_nov_10(fake_http)
    job.run(c, now=at(2026, 10, 18, 14))
    page = fake_http.files["DKT87"]
    fake_http.files["DKT87"] = page.replace(b"User oriented quality report", b"User-oriented quality report")
    assert fake_http.files["DKT87"] != page
    job.run(c, now=at(2026, 11, 10, 14))
    stored = Archive(c.archive_dir).snapshots("elstat", "page-cpi")
    assert len(stored) == 2
    assert LATE_CPI in report_of(c)


def test_eurostat_hicp_release_days_without_new_files_alert(tmp_path, fake_http):
    """PY-JOB-027: Eurostat's HICP release days alert while the datasets' last data update stays the same

    Given a first run that archived Eurostat's HICP datasets
    And Eurostat's calendar with HICP release days on 2026-11-04 and 2026-11-18
    When the run on 2026-11-18 finds the datasets' "last data update" unchanged
    Then its report alerts that both HICP release days brought no new file
    """
    c = cfg(tmp_path)
    job.run(c, now=at(2026, 10, 18, 14))
    job.run(c, now=at(2026, 11, 18, 14))
    assert "Eurostat's HICP: release day 2026-11-04, 2026-11-18, but no new file" in report_of(c)


def test_eurostat_hicp_release_is_confirmed_when_its_files_change(tmp_path, fake_http):
    """PY-JOB-031: Eurostat's HICP release is confirmed once its last data update moves and its files change

    Given HICP release days on 2026-11-04 and 2026-11-18 that brought no new file
    When the datasets' last data update moves, their files change, and the next day's run happens
    Then the HICP's confirmed release day is 2026-11-18
    """
    c = cfg(tmp_path)
    job.run(c, now=at(2026, 10, 18, 14))
    job.run(c, now=at(2026, 11, 18, 14))
    flow = fake_http.files["/dataflow/"]
    fake_http.files["/dataflow/"] = flow.replace(b"2026-10-16T23:00:00+0200", b"2026-11-18T11:00:00+0100")
    assert fake_http.files["/dataflow/"] != flow
    fake_http.files["format=TSV"] = b"tsv.gz bytes, the October release"
    job.run(c, now=at(2026, 11, 19, 14))
    assert job.load_state(c.archive_dir)["release_confirmed"]["eurostat-hicp"] == "2026-11-18"


def test_state_from_before_the_rule_raises_nothing_for_past_days(tmp_path, fake_http):
    """PY-JOB-028: a job state written before this rule counts every past release day as arrived

    Given a job state with a CPI release day on 2026-11-10, a last good run that day, and no confirmed days
    When a forced run happens the next day with nothing new
    Then its report has no late-release alert
    And the CPI's confirmed release day starts at the last good run, 2026-11-10
    """
    c = cfg(tmp_path)
    job.run(c, now=at(2026, 10, 18, 14))
    s = job.load_state(c.archive_dir)
    s.pop("release_confirmed")
    s["release_dates"]["elstat-cpi"].append("2026-11-10")
    s["last_good_run"] = "2026-11-10"
    job.save_state(c.archive_dir, s)
    job.run(c, now=at(2026, 11, 11, 14), force=True)
    assert "but no new file" not in report_of(c)
    assert job.load_state(c.archive_dir)["release_confirmed"]["elstat-cpi"] == "2026-11-10"


def test_a_failed_run_reports_its_failure_not_a_late_release(tmp_path, fake_http):
    """PY-JOB-029: a run with failures on a release day reports the failure, not a late release

    Given a CPI release day on 2026-11-10
    When that day's run fails on one source and brings no new CPI file
    Then the report names the failure but not a late release
    And the CPI release day is still awaited the next day
    """
    c = cfg(tmp_path)
    cpi_release_on_nov_10(fake_http)
    job.run(c, now=at(2026, 10, 18, 14))
    del fake_http.files["puf_en.jsp"]
    r = job.run(c, now=at(2026, 11, 10, 14))
    assert r["result"] == "failures" and "but no new file" not in report_of(c)
    assert job.awaited(job.load_state(c.archive_dir), date(2026, 11, 11))["elstat-cpi"] == [date(2026, 11, 10)]


def test_the_run_log_names_the_release_build_before_it_starts(tmp_path, fake_http, monkeypatch):
    """PY-JOB-030: the run's line in runs.jsonl names the release build it starts

    Given release builds turned on, and a stand-in release build that records its start time
    When the scheduled job runs and stores new files
    Then the build is started with a start time
    And the run's line in runs.jsonl, written before the build starts, names the build by that time
    """
    c, _, _ = _follow_ups(tmp_path, monkeypatch)
    from traceconomics import release

    started = []

    def build(config, reason, now):
        started.append(now)
        assert Archive(c.archive_dir).runs()[-1]["release"] == stamp(now)  # logged already
        return {"id": stamp(now)}

    monkeypatch.setattr(release, "build", build)
    job.run(c, now=at(2026, 10, 18, 14))
    assert len(started) == 1
    assert Archive(c.archive_dir).runs()[-1]["release"] == stamp(started[0])


def test_new_puf_year_raises_an_alert(tmp_path, fake_http):
    """PY-JOB-008: a new year in ELSTAT's microdata catalogue is reported

    Given a first run that stored ELSTAT's microdata catalogue listing HBS 2008 - 2024
    When the catalogue lists 2008 - 2025 and a forced run follows
    Then the latest outbox message names the new listing, "Household Budget Survey (HBS) | 2008 - 2025"
    """
    c = cfg(tmp_path)
    job.run(c, now=at(2026, 10, 18, 14))
    page = fake_http.files["puf_en.jsp"].replace(b"2008 - 2024", b"2008 - 2025")
    fake_http.files["puf_en.jsp"] = page
    job.run(c, now=at(2026, 10, 18, 15), force=True)
    assert "now: Household Budget Survey (HBS) | 2008 - 2025" in outbox(c)[-1].read_text(encoding="utf-8")


def test_failures_keep_the_run_due(tmp_path, fake_http):
    """PY-JOB-009: a run with failures doesn't count as a good run

    Given fake publishers where the microdata catalogue page is missing
    When the scheduled job runs
    Then the result is "failures"
    And no last good run is saved in the job state
    """
    c = cfg(tmp_path)
    del fake_http.files["puf_en.jsp"]
    r = job.run(c, now=at(2026, 10, 18, 14))
    assert r["result"] == "failures"
    assert "last_good_run" not in job.load_state(c.archive_dir)


def test_dry_run_stores_nothing(tmp_path, fake_http):
    """PY-JOB-010: a dry run plans but fetches and stores nothing

    Given fake publishers
    When the scheduled job runs as a dry run
    Then the result is "dry-run" with a non-empty plan
    And no request was made
    And the archive has no index
    """
    c = cfg(tmp_path)
    r = job.run(c, dry_run=True, now=at(2026, 10, 18, 14))
    assert r["result"] == "dry-run" and r["planned"]
    assert not fake_http.requested
    assert not (c.archive_dir / "raw" / "index.jsonl").exists()


def test_morning_run_doesnt_cover_that_days_release(tmp_path, fake_http):
    """PY-JOB-011: a morning run doesn't cover that day's release

    Given fake publishers
    When a forced run happens at 09:00, before the run time
    Then the last good run saved is the day before
    """
    c = cfg(tmp_path)
    job.run(c, now=at(2026, 10, 18, 9), force=True)
    assert job.load_state(c.archive_dir)["last_good_run"] == "2026-10-17"


def test_backup_mark(tmp_path, fake_http):
    """PY-JOB-012: marking the backup done leaves nothing stored since the mark

    Given an archive filled by a run
    When the backup is marked done
    Then the archive lists no file stored since that mark
    """
    c = cfg(tmp_path)
    job.run(c, now=at(2026, 10, 18, 14))
    job.mark_backup_done(c)
    mark = job.load_state(c.archive_dir)["backup_mark"]
    assert Archive(c.archive_dir).stored_since(mark) == []


def _follow_ups(tmp_path, monkeypatch):
    """Release builds on, with stand-ins for the heartbeat, the backup and the release build."""
    from traceconomics import release
    from traceconomics.config import ReleaseConfig

    beats, builds = [], []
    monkeypatch.setattr(job.heartbeat, "send", lambda record: beats.append(record["result"]) or "sent")
    monkeypatch.setattr(job.backup, "sync", lambda root: {"result": "ok", "sent": 1})
    monkeypatch.setattr(release, "build", lambda config, reason, now: builds.append(reason) or {"id": "R1"})
    on = ReleaseConfig(enabled=True, releases_dir=tmp_path / "rel", site_dir=tmp_path / "site")
    return cfg(tmp_path, release=on), beats, builds


def test_heartbeat_backup_and_release_follow_a_run_with_new_data(tmp_path, fake_http, monkeypatch):
    """PY-JOB-013: the heartbeat, backup and release build follow a run with new data

    Given release builds turned on, and stand-ins for the heartbeat, the backup and the release build
    When the scheduled job runs and stores new files
    Then the heartbeat is sent, the backup is ok and the release build's id is recorded
    And there was one release build, and its reason names the Eurostat HICP dataset
    And one heartbeat, for an ok run
    """
    c, beats, builds = _follow_ups(tmp_path, monkeypatch)
    first = job.run(c, now=at(2026, 10, 18, 14))
    assert first["heartbeat"] == "sent" and first["backup"]["result"] == "ok" and first["release"] == "R1"
    assert len(builds) == 1 and "eurostat/prc_hicp_minr" in builds[0]
    assert beats == ["ok"]


def test_a_run_with_nothing_new_has_no_release_and_no_backup(tmp_path, fake_http, monkeypatch):
    """PY-JOB-019: a run with nothing new has no release and no backup

    Given release builds turned on, stand-ins for the follow-ups, and an archive filled by a run
    When a forced run the same day stores nothing new
    Then its record has no release and no backup
    And no release build started after the first run's
    And its heartbeat is sent, for an ok run
    """
    c, beats, builds = _follow_ups(tmp_path, monkeypatch)
    job.run(c, now=at(2026, 10, 18, 14))
    again = job.run(c, now=at(2026, 10, 18, 15), force=True)
    assert again["stored"] == 0
    assert "release" not in again and "backup" not in again
    assert len(builds) == 1
    assert beats == ["ok", "ok"]


def test_a_day_with_no_run_due_still_sends_its_heartbeat(tmp_path, fake_http, monkeypatch):
    """PY-JOB-020: a day with no run due still sends its heartbeat

    Given release builds turned on, stand-ins for the follow-ups, and an archive filled by a run
    When the next day's job finds no run due
    Then its result is "not-due" and its heartbeat is sent, for a not-due day
    And no release build started after the first run's

    The heartbeat goes out every day, due or not, so the watchdog can tell a quiet day from a dead
    machine.
    """
    c, beats, builds = _follow_ups(tmp_path, monkeypatch)
    job.run(c, now=at(2026, 10, 18, 14))
    quiet = job.run(c, now=at(2026, 10, 19, 14))
    assert quiet["result"] == "not-due" and quiet["heartbeat"] == "sent"
    assert len(builds) == 1
    assert beats == ["ok", "not-due"]


def test_release_is_off_by_default(tmp_path, fake_http, monkeypatch):
    """PY-JOB-014: release builds are off by default

    Given a configuration with no release section
    When the scheduled job runs and stores new files
    Then no release build starts
    And the run record has no release
    """
    from traceconomics import release

    monkeypatch.setattr(release, "build", lambda *a, **k: pytest.fail("no release on a machine without [release]"))
    assert "release" not in job.run(cfg(tmp_path), now=at(2026, 10, 18, 14))


# -- visit counts (exported every day, due or not) ---------------------------


def _not_due_state(tmp_path):
    root = tmp_path / "archive"
    (root / "state").mkdir(parents=True)
    job.save_state(root, state_with([date(2026, 11, 10)], "2026-11-10"))


def test_a_quiet_day_still_exports_visit_counts_and_backs_them_up(tmp_path, monkeypatch):
    """PY-JOB-015: a day with no run due still exports visit counts and backs them up

    Given a job state with no release due, an analytics stand-in that stores one day of visits and has downloads off, and stand-ins for the backup and heartbeat
    When the scheduled job runs
    Then the result is "not-due", with one analytics file stored and the backup ok
    And the downloads export is "off"
    And the visits export ran once, for today, and the backup ran once
    And the saved visits bookmark is the stored day
    """
    _not_due_state(tmp_path)
    seen, synced = [], []

    def fake_export(archive, state, today, feed):
        if feed is not job.analytics.VISITS:
            return {"result": "off"}
        seen.append(today)
        archive.store_bytes(
            "cloudflare",
            "web-analytics",
            b'{"day": "2026-11-11"}\n',
            url=None,
            retrieved_at=datetime(2026, 11, 12, 11, tzinfo=ZoneInfo("UTC")),
            ext=".json",
            extra={"day": "2026-11-11"},
        )
        state["analytics_through"] = "2026-11-11"
        return {"result": "ok", "days": ["2026-11-11"], "stored": 1}

    monkeypatch.setattr(job.analytics, "export", fake_export)
    monkeypatch.setattr(job.backup, "sync", lambda root: synced.append(root) or {"result": "ok", "sent": 1})
    monkeypatch.setattr(job.heartbeat, "send", lambda record: "sent")
    rec = job.run(cfg(tmp_path), now=at(2026, 11, 12, 13))
    assert rec["result"] == "not-due" and rec["analytics"]["stored"] == 1 and rec["backup"]["result"] == "ok"
    assert rec["downloads"] == {"result": "off"}
    assert seen == [date(2026, 11, 12)] and len(synced) == 1
    assert job.load_state(tmp_path / "archive")["analytics_through"] == "2026-11-11"


def test_the_bookmark_is_rebuilt_from_the_archive(tmp_path, monkeypatch):
    """PY-JOB-016: a lost analytics bookmark is rebuilt from the archive

    Given no bookmark in the job state, and stored visit days of which one was a later manual fill of an older day and one is today's
    When the analytics export runs
    Then the bookmark it is given is the latest finished day in the archive, not the last stored nor today's
    """
    archive = Archive(tmp_path / "archive")
    # Stored last but not the latest day (a manual fill), and today's, not over yet: neither counts.
    for day, stored_hour in (("2026-11-09", 11), ("2026-11-05", 12), ("2026-11-12", 13)):
        archive.store_bytes(
            "cloudflare",
            "web-analytics",
            f'{{"day": "{day}"}}\n'.encode(),
            url=None,
            retrieved_at=datetime(2026, 11, 12, stored_hour, tzinfo=ZoneInfo("UTC")),
            ext=".json",
            extra={"day": day},
        )
    seen = []
    monkeypatch.setattr(
        job.analytics, "export", lambda archive, state, today, feed: seen.append(dict(state)) or {"result": "off"}
    )
    job.export_analytics(cfg(tmp_path), archive, {}, at(2026, 11, 12, 13))
    assert seen[0]["analytics_through"] == "2026-11-09"


@pytest.mark.parametrize("through, alerts", [("2026-11-10", 0), ("2026-11-07", 1), (None, 1)])
def test_a_failing_export_alerts_only_when_days_are_running_out(tmp_path, monkeypatch, through, alerts):
    """PY-JOB-017: a failing analytics export alerts only when days are running out

    Given a visits bookmark that is recent, several days old, or missing
    And an analytics export that fails
    When the analytics export runs
    Then an alert is sent only for the old or missing bookmark, never for the recent one
    And every alert's subject starts with "ALERT: analytics export"
    """
    sent = []
    monkeypatch.setattr(job, "notify", lambda config, subject, body: sent.append(subject) or "outbox")
    monkeypatch.setattr(
        job.analytics, "export", lambda archive, state, today, feed: {"result": "failed", "error": "401"}
    )
    state = {} if through is None else {"analytics_through": through}
    job.export_analytics(cfg(tmp_path), Archive(tmp_path / "archive"), state, at(2026, 11, 12, 13))
    assert len(sent) == alerts and all(s.startswith("ALERT: analytics export") for s in sent)


def test_each_feed_has_its_own_bookmark_and_alert(tmp_path, monkeypatch):
    """PY-JOB-018: each analytics feed has its own bookmark and alert

    Given a visits bookmark, no downloads bookmark and a stored downloads day five days back
    And a downloads export that fails
    When the downloads export runs
    Then it is given the visits bookmark untouched plus a downloads bookmark rebuilt from the archive
    And one alert is sent, titled "ALERT: analytics export (downloads) failing, 4 days not copied"
    And its body says how many days Cloudflare keeps (31) and gives the command with "--feed downloads"
    """
    archive = Archive(tmp_path / "archive")
    archive.store_bytes(
        "cloudflare",
        "downloads",
        b'{"day": "2026-11-07"}\n',
        url=None,
        retrieved_at=datetime(2026, 11, 9, 11, tzinfo=ZoneInfo("UTC")),
        ext=".json",
        extra={"day": "2026-11-07"},
    )
    sent, seen = [], []
    monkeypatch.setattr(job, "notify", lambda config, subject, body: sent.append((subject, body)) or "outbox")
    monkeypatch.setattr(
        job.analytics,
        "export",
        lambda archive, state, today, feed: seen.append(dict(state)) or {"result": "failed", "error": "403"},
    )
    state = {"analytics_through": "2026-11-11"}
    job.export_analytics(cfg(tmp_path), archive, state, at(2026, 11, 12, 13), job.analytics.DOWNLOADS)
    assert seen[0] == {"analytics_through": "2026-11-11", "downloads_through": "2026-11-07"}
    ((subject, body),) = sent
    assert subject == "ALERT: analytics export (downloads) failing, 4 days not copied"
    assert "31 days" in body and "--feed downloads" in body
