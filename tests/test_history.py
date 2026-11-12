from datetime import date
from pathlib import Path

import pytest

from traceconomics.archive.store import Archive
from traceconomics.cli import _years
from traceconomics.sources import base
from traceconomics.sources.elstat import history

pytestmark = pytest.mark.unit

FIX = Path(__file__).parent / "fixtures"

# Document titles as they appear on ELSTAT's archived page DKT87/2015-M12.
MONTH_PAGE = b"""<html><body><table>
<tr><td><a href="/en/statistics?x=1&_documentID=114839&_locale=en">06. Monthly sub-indices of groups of items
 of CPI (2020=100.0) (January 1999 - September 2026)</a></td></tr>
<tr><td><a href="/en/statistics?x=1&_documentID=114865&_locale=en">07. Monthly sub-indices of CPI groups,
 sub-groups and items (2020=100.0) (January 2015 - December 2015)</a></td></tr>
<tr><td><a href="/en/statistics?x=1&_documentID=114854&_locale=en">08. Monthly evolution of Goods, Services
 and Core Index (2020=100.0) (January 2009 - September 2026)</a></td></tr>
</table></body></html>"""


class FakeHttp:
    """Serves `files` ({part of the URL: bytes}); an Excel file comes with a file name, as ELSTAT
    sends one, so it is stored with its extension."""

    def __init__(self, files):
        self.files, self.requested = files, []

    def download(self, url, dest):
        self.requested.append(url)
        for key, content in self.files.items():
            if key in url:
                dest.write_bytes(content)
                headers = (
                    {"content-disposition": 'attachment; filename="table.xls"'}
                    if content.startswith(b"\xd0\xcf\x11\xe0")
                    else {}
                )
                return base.Response(url=url, status=200, headers=headers, retrieved_at=base.utc_now())
        raise base.FetchError(f"{url}: 404")


def test_years_argument():
    """PY-CPIHIST-001: the years argument takes ranges and single years

    Given the years argument "2011-2013,2015"
    When it is read
    Then it gives 2011, 2012, 2013 and 2015
    """
    assert _years("2011-2013,2015") == [2011, 2012, 2013, 2015]


def test_finds_the_years_table07():
    """PY-CPIHIST-002: the year's table 07 is found on the archived month page

    Given ELSTAT's archived month page listing tables 06, 07 and 08
    When table 07 is looked for, for 2015 and for 2016
    Then 2015 gives document 114865
    And 2016, which the page doesn't list, gives None
    """
    assert history.table07_doc(MONTH_PAGE, 2015)[0] == "114865"
    assert history.table07_doc(MONTH_PAGE, 2016) is None


def test_check_accepts_the_real_2025_file_and_rejects_a_wrong_year():
    """PY-CPIHIST-003: the table 07 check accepts the right year and flags a wrong one

    Given the real CPI table 07 for 2025
    When it is checked as 2025 and as 2024
    Then checking it as 2025 finds no problems
    And checking it as 2024 reports a problem naming 2024
    """
    assert history.check_table07(FIX / "elstat_cpi07_2025.xls", 2025) == []
    assert any("2024" in p for p in history.check_table07(FIX / "elstat_cpi07_2025.xls", 2024))


def ctx_with(tmp_path, files):
    http = FakeHttp(files)
    return base.RunContext(archive=Archive(tmp_path), http=http, today=date(2026, 10, 18)), http


@pytest.mark.integration
def test_fetches_page_and_both_languages_once(tmp_path):
    """PY-CPIHIST-004: a past year's page and table are fetched in both languages, once

    Given a fake ELSTAT serving the 2015 month page and a table 07 file
    When the history for 2015 is fetched
    And fetched again into the same archive
    Then the first fetch stores the month page and the table in English and Greek are stored
    And the Greek table is requested with "_locale=el"
    And two alerts are raised, the first naming 2015, since the file is in fact the 2025 table
    And the second fetch requests no document

    The fixture is the 2025 table, so the check must flag it as the wrong year.
    """
    xls = (FIX / "elstat_cpi07_2025.xls").read_bytes()
    ctx, http = ctx_with(tmp_path, {"DKT87/2015-M12": MONTH_PAGE, "documentID=114865": xls})
    history.fetch_years(ctx, [2015])
    stored = {r.dataset for r in ctx.results if r.status == "stored"}
    assert stored == {"page-cpi-2015-M12", "doc-114865", "doc-114865-el"}
    assert any("_locale=el" in u for u in http.requested)
    # The fixture is the 2025 table, so the check must flag it as the wrong year.
    assert len(ctx.alerts) == 2 and all("title doesn't name 2015" in a for a in ctx.alerts)

    ctx2, http2 = ctx_with(tmp_path, {"DKT87/2015-M12": MONTH_PAGE, "documentID=114865": xls})
    history.fetch_years(ctx2, [2015])
    assert not any("documentID" in u for u in http2.requested)  # already archived: not fetched again


@pytest.mark.integration
def test_missing_table_is_a_failure(tmp_path):
    """PY-CPIHIST-005: a year without table 07 is a failure

    Given a month page for 2016 that doesn't list a 2016 table 07
    When the history for 2016 is fetched
    Then a failure naming 2016 is recorded
    """
    ctx, _ = ctx_with(tmp_path, {"DKT87/2016-M12": MONTH_PAGE})
    history.fetch_years(ctx, [2016])
    assert ctx.failures and "2016" in ctx.failures[0]


PAGE_2025 = MONTH_PAGE.replace(b"January 2015 - December 2015", b"January 2025 - December 2025")


@pytest.mark.integration
def test_the_right_years_table_is_stored_and_noted_as_checked(tmp_path):
    """PY-CPIHIST-006: the right year's table 07 is stored and noted as checked

    Given a fake ELSTAT serving the 2025 month page and the real 2025 table 07
    When the history for 2025 is fetched
    Then no alert is raised
    And the notes say each language's table was stored and checked
    """
    xls = (FIX / "elstat_cpi07_2025.xls").read_bytes()
    ctx, _ = ctx_with(tmp_path, {"DKT87/2025-M12": PAGE_2025, "documentID=114865": xls})
    notes = history.fetch_years(ctx, [2025])
    assert not ctx.alerts
    assert notes == [
        "2025 en: doc-114865 stored, checked (COICOP 2018, 2020=100)",
        "2025 el: doc-114865-el stored, checked (COICOP 2018, 2020=100)",
    ]


@pytest.mark.integration
def test_a_page_or_table_that_cant_be_fetched_is_a_failure_not_a_crash(tmp_path):
    """PY-CPIHIST-007: a month page or table that can't be fetched is a failure, not a crash

    Given a fake ELSTAT that serves the 2025 month page but not its table, and no page for 2024
    When the history for 2024 and 2025 is fetched
    Then three failures are recorded: the 2024 page and both languages' 2025 table
    And nothing but the 2025 page is stored
    """
    ctx, _ = ctx_with(tmp_path, {"DKT87/2025-M12": PAGE_2025})
    history.fetch_years(ctx, [2024, 2025])
    assert len(ctx.failures) == 3 and "page-cpi-2024-M12" in ctx.failures[0]
    assert [r.dataset for r in ctx.results] == ["page-cpi-2025-M12"]


@pytest.mark.parametrize(
    "name, problem",
    [
        ("elstat_cpi07_2011_el.xls", None),
        ("elstat_cpi07_2026.xlsx", "can't read the file"),
        ("elstat_hbs_t103_2018.xls", "no sheet named INDICES or ΔΕΙΚΤΕΣ"),
    ],
)
def test_the_table07_check_on_other_files(name, problem):
    """PY-CPIHIST-008: the table 07 check passes the Greek file and flags files that aren't a table 07

    Given ELSTAT's Greek table 07 for 2011, its 2026 table as .xlsx, and a household survey table
    When each is checked as its year's table 07
    Then the Greek table passes (its title says "έτους 2011" and 2020=100)
    And the .xlsx file can't be read by the .xls reader
    And the survey table has no indices sheet
    """
    year = int(name.split("_")[2][:4]) if name.startswith("elstat_cpi07") else 2018
    problems = history.check_table07(FIX / name, year)
    assert problems == [] if problem is None else (len(problems) == 1 and problems[0].startswith(problem))


def test_the_table07_check_names_a_wrong_base_and_a_missing_coicop_column(monkeypatch):
    """PY-CPIHIST-009: the table 07 check names an old base and a header without the COICOP 2018 column

    Given a sheet named INDICES whose title is for 2015 on the 2009 base and whose header lacks COICOP18
    When it is checked as the 2015 table 07
    Then it reports that the title doesn't say 2020=100
    And that the header has no COICOP18 column
    """

    class Sheet:
        def row_values(self, r):
            return {0: ["Monthly sub-indices for 2015 (2009=100.0)"], 2: ["COICOP", "ITEMS"]}.get(r, [])

    class Book:
        def sheet_names(self):
            return ["INDICES "]

        def sheet_by_name(self, name):
            return Sheet()

    monkeypatch.setattr(history.xlrd, "open_workbook", lambda path, on_demand: Book())
    assert history.check_table07(Path("x.xls"), 2015) == ["title doesn't say 2020=100", "header has no COICOP18 column"]


@pytest.mark.integration
def test_a_history_fetch_is_reported_and_logged_like_a_run(tmp_path, monkeypatch):
    """PY-CPIHIST-010: a history fetch is reported and logged like a run

    Given a configuration without email and a fake ELSTAT serving the 2025 page and table, but no 2024 page
    When the history for 2024 and 2025 is fetched for real
    Then the result is "failures", with the 2024 page named and three new files stored
    And a report flagged ALERT is in the outbox, listing the failure and the stored tables
    And the run is logged in the archive
    """
    from traceconomics import job
    from traceconomics.config import Config

    xls = (FIX / "elstat_cpi07_2025.xls").read_bytes()
    http = FakeHttp({"DKT87/2025-M12": PAGE_2025, "documentID=114865": xls})
    monkeypatch.setattr(job, "HttpClient", lambda *a, **k: http)
    c = Config(archive_dir=tmp_path, user_agent="t")
    record = job.fetch_history(c, [2024, 2025], pause_seconds=0)
    assert record["result"] == "failures" and record["stored"] == 3
    assert len(record["failures"]) == 1 and "2024" in record["failures"][0]
    report = Path(record["report"]).read_text(encoding="utf-8")
    assert "ALERT: history fetch: 3 new, 1 failed" in report and "FAILURES:" in report
    assert "2025 en: doc-114865 stored, checked" in report
    assert Archive(tmp_path).runs()[-1]["reason"] == "history fetch, CPI table 07 2024,2025"


def test_a_lock_left_by_a_dead_run_is_taken_over(tmp_path):
    """PY-CPIHIST-011: a lock left behind by a run that died is taken over once it is stale

    Given a lock file older than the stale-lock limit, as a crashed run would leave
    When a new run takes the lock
    Then it succeeds and the lock file holds the new run's process ID
    And after the run the lock is gone
    """
    import os

    from traceconomics import job

    lock = tmp_path / job.LOCK_FILE
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("12345", encoding="utf-8")
    old = lock.stat().st_mtime - job.STALE_LOCK.total_seconds() - 60
    os.utime(lock, (old, old))
    with job.RunLock(tmp_path):
        assert lock.read_text(encoding="utf-8") == str(os.getpid())
    assert not lock.exists()
