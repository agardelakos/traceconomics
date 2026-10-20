from datetime import date
from pathlib import Path

from traceconomics.archive.store import Archive
from traceconomics.cli import _years
from traceconomics.sources import base
from traceconomics.sources.elstat import history

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
    def __init__(self, files):
        self.files, self.requested = files, []

    def download(self, url, dest):
        self.requested.append(url)
        for key, content in self.files.items():
            if key in url:
                dest.write_bytes(content)
                return base.Response(url=url, status=200, headers={}, retrieved_at=base.utc_now())
        raise base.FetchError(f"{url}: 404")


def test_years_argument():
    assert _years("2011-2013,2015") == [2011, 2012, 2013, 2015]


def test_finds_the_years_table07():
    assert history.table07_doc(MONTH_PAGE, 2015)[0] == "114865"
    assert history.table07_doc(MONTH_PAGE, 2016) is None


def test_check_accepts_the_real_2025_file_and_rejects_a_wrong_year():
    assert history.check_table07(FIX / "elstat_cpi07_2025.xls", 2025) == []
    assert any("2024" in p for p in history.check_table07(FIX / "elstat_cpi07_2025.xls", 2024))


def ctx_with(tmp_path, files):
    http = FakeHttp(files)
    return base.RunContext(archive=Archive(tmp_path), http=http, today=date(2026, 10, 18)), http


def test_fetches_page_and_both_languages_once(tmp_path):
    xls = (FIX / "elstat_cpi07_2025.xls").read_bytes()
    ctx, http = ctx_with(tmp_path, {"DKT87/2015-M12": MONTH_PAGE, "documentID=114865": xls})
    history.fetch_years(ctx, [2015])
    stored = {r.dataset for r in ctx.results if r.status == "stored"}
    assert stored == {"page-cpi-2015-M12", "doc-114865", "doc-114865-el"}
    assert any("_locale=el" in u for u in http.requested)
    # The fixture is the 2025 table, so the check must flag it as the wrong year.
    assert len(ctx.alerts) == 2 and "2015" in ctx.alerts[0]

    ctx2, http2 = ctx_with(tmp_path, {"DKT87/2015-M12": MONTH_PAGE, "documentID=114865": xls})
    history.fetch_years(ctx2, [2015])
    assert not any("documentID" in u for u in http2.requested)  # already archived: not fetched again


def test_missing_table_is_a_failure(tmp_path):
    ctx, _ = ctx_with(tmp_path, {"DKT87/2016-M12": MONTH_PAGE})
    history.fetch_years(ctx, [2016])
    assert ctx.failures and "2016" in ctx.failures[0]
