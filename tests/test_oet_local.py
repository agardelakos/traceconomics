"""Our own weights tables: written by the local run, read into the store. Made-up numbers only."""

from datetime import UTC, datetime

import duckdb
import pytest

from traceconomics.archive.store import Archive
from traceconomics.checks import FormatError
from traceconomics.sources import oet_local
from traceconomics.store.build import Store, update
from traceconomics.store.query import as_of, open_views

pytestmark = pytest.mark.unit

WEIGHTS = """# Greek household budget survey 2016: made up
# provenance: {}
geo,ref_year,grouping,group,imputed_rent,hh_weighting,tutoring,coicop18,digits,leaf,share,se,rse,high_rse,n_households_unweighted,reliability,se_design,classification_native,source_version
GR,2016,all,all,excluded,plutocratic,priced,01,2,False,0.25,0.004,0.016,False,6000,normal,full,ecoicop1,x
GR,2016,B,Q1,excluded,plutocratic,priced,01111,5,True,0.001,0.0004,0.4,True,<20,suppressed,full,ecoicop1,x
GR,2016,B,Q1,included,plutocratic,priced,01111,5,True,0.0008,,,,<20,suppressed,unavailable,ecoicop1,x
"""
GROUPS = """# made up
geo,ref_year,grouping,group,n_households,households_weighted,people_weighted,uncovered_purchases_share,se_design,se_note,source_version
GR,2016,all,all,6000,4100000.5,10300000,0.0355,full,2016: strata HA06,x
"""


def named(rows, fmt):
    cols = [*oet_local.FORMATS[fmt]["dims"], "measure", "ref_period", "value_text", "value"]
    return [dict(zip(cols, r)) for r in rows]


def test_rows_are_one_value_each_and_keep_text(tmp_path):
    """PY-OETLOCAL-001: a weights table becomes one row per value, keeping its text

    Given a made-up weights CSV with a spending column, including a "<20" count and an empty standard error
    When it is read as oet-weights
    Then a share keeps its text "0.25" and its value 0.25
    And the "<20" count keeps its text and has no value
    And the reliability is kept as text ("suppressed")
    And an empty cell gives no row
    And every row has reference period 2016 and spending "purchases"
    """
    p = tmp_path / "w.csv"
    p.write_text(
        WEIGHTS.replace("group,imputed_rent", "group,spending,imputed_rent")
        .replace(",all,all,", ",all,all,purchases,")
        .replace(",B,Q1,", ",B,Q1,purchases,"),
        encoding="utf-8",
    )
    rows = named(oet_local.rows(p, "oet-weights"), "oet-weights")
    by = {(r["group"], r["imputed_rent"], r["measure"]): r for r in rows}
    assert (by[("all", "excluded", "share")]["value_text"], by[("all", "excluded", "share")]["value"]) == ("0.25", 0.25)
    assert by[("Q1", "excluded", "n_households_unweighted")]["value_text"] == "<20"
    assert by[("Q1", "excluded", "n_households_unweighted")]["value"] is None
    assert by[("Q1", "excluded", "reliability")]["value_text"] == "suppressed"
    assert ("Q1", "included", "se") not in by  # empty: no row
    assert all(r["ref_period"] == "2016" and r["spending"] == "purchases" for r in rows)


def test_files_from_before_the_spending_dimension_read_as_all_modes(tmp_path):
    """PY-OETLOCAL-002: files from before the spending dimension read as all modes

    Given a made-up weights CSV without a spending column
    When it is read as oet-weights
    Then every row's spending is "all"
    """
    p = tmp_path / "w.csv"
    p.write_text(WEIGHTS, encoding="utf-8")
    assert {r["spending"] for r in named(oet_local.rows(p, "oet-weights"), "oet-weights")} == {"all"}


def test_duplicate_or_missing_columns_are_refused(tmp_path):
    """PY-OETLOCAL-003: duplicate rows and missing columns are refused

    Given a made-up weights CSV with a row repeated
    And a made-up groups CSV missing the people_weighted column
    When each is read
    Then the weights CSV raises a FormatError about a "duplicate"
    And the groups CSV raises a FormatError naming people_weighted
    """
    p = tmp_path / "w.csv"
    lines = WEIGHTS.splitlines()
    p.write_text("\n".join(lines + [lines[-1]]), encoding="utf-8")
    with pytest.raises(FormatError, match="duplicate"):
        list(oet_local.rows(p, "oet-weights"))
    p.write_text(GROUPS.replace("people_weighted", "people"), encoding="utf-8")
    with pytest.raises(FormatError, match="people_weighted"):
        list(oet_local.rows(p, "oet-groups"))


@pytest.mark.integration
def test_archived_tables_reach_the_store(tmp_path):
    """PY-OETLOCAL-004: archived weights and groups tables reach the store

    Given made-up weights and groups tables archived under oet-local
    When the store is updated from them
    Then 11 weights rows and 5 groups rows are added (one standard error is empty)
    And the all-households share reads back as 0.25 for 01 in 2016
    And the uncovered purchases share reads back as 0.0355
    """
    archive, store = Archive(tmp_path / "a"), Store(tmp_path / "s")
    when = datetime(2026, 10, 19, 12, tzinfo=UTC)
    for dataset, text in (("hbs-weights-gr-2016", WEIGHTS), ("hbs-groups-gr-2016", GROUPS)):
        archive.store_bytes(
            "oet-local",
            dataset,
            text.encode("utf-8"),
            url=None,
            retrieved_at=when,
            ext=".csv",
            kind="local",
            extra={"original_name": f"{dataset}.csv"},
        )
    con = duckdb.connect()
    reports = update(archive, store, con, only=["oet-local:hbs_weights", "oet-local:hbs_groups"])
    assert [r.added for r in reports] == [11, 5]  # 4 + 4 + 3 (one se is empty); 5
    open_views(con, store.root)
    share = as_of(con, "oet-local:hbs_weights", where="measure = 'share' AND \"group\" = 'all'")
    assert share.project("value, coicop18, ref_period").fetchall() == [(0.25, "01", "2016")]
    unc = as_of(con, "oet-local:hbs_groups", where="measure = 'uncovered_purchases_share'")
    assert unc.project("value").fetchall() == [(0.0355,)]


def test_csv_writes_small_counts_as_text_and_is_repeatable():
    """PY-OETLOCAL-005: the CSV writes small counts as text and is repeatable

    Given counts of 19 and 20, and a table with a missing number and a missing text
    When the counts are formatted and the table is written twice as CSV with a header
    Then 19 is written "<20" and 20 as "20"
    And both writes are the same bytes, the header as a comment and missing values as empty cells

    Needs pandas (skipped without the local extra).
    """
    pd = pytest.importorskip("pandas")
    from traceconomics.local import weights

    assert weights._count(19) == "<20" and weights._count(20) == "20"
    t = pd.DataFrame({"a": [0.1, float("nan")], "b": ["x", pd.NA]})
    assert weights.to_csv(t, ["h"]) == weights.to_csv(t, ["h"]) == b"# h\na,b\n0.1,x\n,\n"


def test_bands_file_has_many_periods_per_series(tmp_path):
    """PY-OETLOCAL-006: a bands file has many periods per series

    Given a made-up bands CSV with one series over two months
    And one with the same month twice
    When each is read as oet-bands
    Then the first gives rows for 2022-01 and 2022-02
    And the second raises a FormatError about a "duplicate"
    """
    p = tmp_path / "b.csv"
    head = "geo,grouping,group,spending,imputed_rent,price_source,weights_timing,unit,ref_period,se\n"
    row = "GR,B,Q1,purchases,excluded,cpi,N,RCH_A,{},0.1\n"
    p.write_text("# x\n" + head + row.format("2022-01") + row.format("2022-02"), encoding="utf-8")
    assert [r[-3] for r in oet_local.rows(p, "oet-bands")] == ["2022-01", "2022-02"]
    p.write_text("# x\n" + head + row.format("2022-01") + row.format("2022-01"), encoding="utf-8")
    with pytest.raises(FormatError, match="duplicate"):
        list(oet_local.rows(p, "oet-bands"))


def test_limits_file_reads_one_row_per_fifth(tmp_path):
    """PY-OETLOCAL-007: an income limits file is read per fifth

    Given a made-up limits CSV for Q1 and Q2, Q2 without a standard error
    When it is read as oet-limits
    Then Q1's limit is a row with text "7400" and value 7400.0
    And Q2's design "unavailable" is a row with text only
    And Q2 has no standard error row
    """
    p = tmp_path / "l.csv"
    p.write_text(
        "# x\ngeo,ref_year,grouping,group,unit,limit,se,se_design,source_version\n"
        "GR,2024,B,Q1,EUR_PER_ADULT_EQ_Y,7400,52.5,full,v\n"
        "GR,2024,B,Q2,EUR_PER_ADULT_EQ_Y,10600,,unavailable,v\n",
        encoding="utf-8",
    )
    got = list(oet_local.rows(p, "oet-limits"))
    assert ("GR", "B", "Q1", "EUR_PER_ADULT_EQ_Y", "limit", "2024", "7400", 7400.0) in got
    assert ("GR", "B", "Q2", "EUR_PER_ADULT_EQ_Y", "se_design", "2024", "unavailable", None) in got
    assert not [r for r in got if r[1:5] == ("B", "Q2", "EUR_PER_ADULT_EQ_Y", "se")]  # an empty se is no row


def test_household_types_file_reads_ours_and_elstats(tmp_path):
    """PY-OETLOCAL-011: a household types file is read with ours and ELSTAT's shares, agreement and status

    Given a made-up household types CSV for 2023 with two types, ELSTAT's marked unusable and one count written "<20"
    When it is read as oet-hhtypes
    Then each type has rows for our share and ELSTAT's share as numbers
    And the agreement is a number and the status a text row
    And the small count stays as text with no number
    """
    p = tmp_path / "t.csv"
    p.write_text(
        "# x\ngeo,ref_year,group,n_households,share_households,elstat_n_households,elstat_share_households,"
        "agreement,elstat_status,source_version\n"
        "GR,2023,A1,812,0.25,1004,0.31,0.269,unusable: broken,v\n"
        "GR,2023,A1_DCH,<20,0.004,55,0.02,0.269,unusable: broken,v\n",
        encoding="utf-8",
    )
    got = list(oet_local.rows(p, "oet-hhtypes"))
    assert ("GR", "A1", "share_households", "2023", "0.25", 0.25) in got
    assert ("GR", "A1", "elstat_share_households", "2023", "0.31", 0.31) in got
    assert ("GR", "A1", "agreement", "2023", "0.269", 0.269) in got
    assert ("GR", "A1", "elstat_status", "2023", "unusable: broken", None) in got
    assert ("GR", "A1_DCH", "n_households", "2023", "<20", None) in got


def test_rent_file_reads_one_row_per_tenure_and_measure(tmp_path):
    """PY-OETLOCAL-012: a rent file is read per tenure, with rent paid in euros

    Given a made-up rent CSV for 2024 with all households and renters, the renters' count written "<20"
    When it is read as oet-rent
    Then each tenure has rows for its households, people and rent paid as numbers
    And the small count stays as text with no number
    """
    p = tmp_path / "r.csv"
    p.write_text(
        "# x\ngeo,ref_year,tenure,n_households,households_weighted,people_weighted,rent_paid_eur,source_version\n"
        "GR,2024,all,6000,4299000.5,10400000.25,3501000000.75,v\n"
        "GR,2024,renter,<20,812000.5,1900000,3501000000.75,v\n",
        encoding="utf-8",
    )
    got = list(oet_local.rows(p, "oet-rent"))
    assert ("GR", "all", "rent_paid_eur", "2024", "3501000000.75", 3501000000.75) in got
    assert ("GR", "renter", "households_weighted", "2024", "812000.5", 812000.5) in got
    assert ("GR", "renter", "n_households", "2024", "<20", None) in got


def test_spending_file_reads_each_columns_figures_and_results(tmp_path):
    """PY-OETLOCAL-013: a spending check file is read per column and item, with ELSTAT's figure, ours and the result

    Given a made-up spending check CSV for 2014: all households' totals, an item that differs and one the file has no column for, and an income band's item
    When it is read as oet-spending
    Then each item has rows for its name and result as text and ELSTAT's figure and ours as numbers
    And an item without our figure has no row for it
    And the band is a column of its own
    """
    p = tmp_path / "s.csv"
    p.write_text(
        "# x\ngeo,ref_year,group,coicop,item,published,ours,result,source_version\n"
        "GR,2014,All households,households,,4152372,4136073,differs,v\n"
        "GR,2014,All households,01112,Bread,9.5,9.43,differs,v\n"
        "GR,2014,All households,03111,Clothing materials,0.09,,differs,v\n"
        "GR,2014,up 750 €,01112,Bread,6.1,6.1,matched,v\n",
        encoding="utf-8",
    )
    got = list(oet_local.rows(p, "oet-spending"))
    assert ("GR", "All households", "households", "ours", "2014", "4136073", 4136073.0) in got
    assert ("GR", "All households", "01112", "item", "2014", "Bread", None) in got
    assert ("GR", "All households", "01112", "published", "2014", "9.5", 9.5) in got
    assert ("GR", "All households", "01112", "result", "2014", "differs", None) in got
    assert not [r for r in got if r[2] == "03111" and r[3] == "ours"]
    assert ("GR", "up 750 €", "01112", "result", "2014", "matched", None) in got


@pytest.mark.integration
def test_an_empty_limits_file_withdraws_the_earlier_limits(tmp_path):
    """PY-OETLOCAL-016: a limits file with no rows withdraws the year's earlier limits, rather than failing

    Given a made-up 2010 limits table for Q1 and Q2 archived and loaded into the store
    And then a newer 2010 limits file with its header and no rows (a survey whose incomes can't rank households)
    When the store is updated again
    Then the update adds nothing and withdraws the six earlier values
    And no 2010 limit is left in the store
    """
    archive, store = Archive(tmp_path / "a"), Store(tmp_path / "s")
    head = "# x\ngeo,ref_year,grouping,group,unit,limit,se,se_design,source_version\n"
    full = head + ("GR,2010,B,Q1,EUR_PER_ADULT_EQ_Y,4797,50,full,v\nGR,2010,B,Q2,EUR_PER_ADULT_EQ_Y,8167,60,full,v\n")
    con = duckdb.connect()
    for day, text in ((19, full), (20, head)):
        archive.store_bytes(
            "oet-local",
            "hbs-limits-gr-2010",
            text.encode("utf-8"),
            url=None,
            retrieved_at=datetime(2026, 10, day, 12, tzinfo=UTC),
            ext=".csv",
            kind="local",
            extra={"original_name": "hbs-limits-gr-2010.csv"},
        )
    reports = update(archive, store, con, only=["oet-local:hbs_limits"])
    assert (reports[0].added, reports[0].withdrawn) == (6, 6)
    open_views(con, store.root)
    assert as_of(con, "oet-local:hbs_limits").fetchall() == []
