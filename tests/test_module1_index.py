"""Group indices end to end on made-up prices and baskets."""

import pytest

from traceconomics.checks import FormatError
from traceconomics.module1 import index, output
from traceconomics.module1.weights_used import Basket

pytestmark = pytest.mark.unit


def flat_year(y, start, end):
    """A block for year y: December y-1 at `start`, every month of y at `end`."""
    return {f"{y - 1}-12": start, **{f"{y}-{m:02d}": end for m in range(1, 13)}}


def blocks(first=2008, last=2026):
    b = {}
    for y in range(first, last + 1):
        b[y] = {"01": flat_year(y, 100.0, 110.0 if y == 2022 else 100.0), "04": flat_year(y, 100.0, 100.0)}
    return b


def baskets(food_q1=0.6, food_q5=0.2):
    out = {}
    for y in range(2008, 2025):  # surveys 2008-2024, as held today
        for g, f in (("Q1", food_q1), ("Q5", food_q5)):
            out[(y, "B", g)] = Basket({"01": f, "04": 1 - f}, {"01": "normal", "04": "normal"})
    return out


def test_a_price_rise_in_one_item_moves_groups_by_their_share():
    """PY-INDEX-001: a price rise in one item moves each group by its share

    Given made-up prices where food rises 10% through 2022 and nothing else moves
    And baskets for surveys 2008 to 2024 with food at 60% for Q1 and 20% for Q5
    When the B/Q1 and B/Q5 series are built
    Then Q1's annual rate at 2022-12 is about 6.0 and Q5's about 2.0 (within 0.05)
    And Q1's links run from 2009 to 2026
    And 2026's link is a "first" estimate on survey 2023, the newest out on 2026-01-01
    And Q1's index averages 100 over 2025
    """
    b, k = blocks(), baskets()
    q1 = index.build(None, "B", "Q1", blocks=b, baskets=k)
    q5 = index.build(None, "B", "Q5", blocks=b, baskets=k)
    # Food is up 10% through 2022, flat otherwise: Q1 (60% food) about 6%, Q5 (20% food) about 2%.
    assert q1.rates()["2022-12"]["annual"] == pytest.approx(6.0, abs=0.05)
    assert q5.rates()["2022-12"]["annual"] == pytest.approx(2.0, abs=0.05)
    assert q1.schedule[0].year == 2009 and q1.schedule[-1].year == 2026
    # Survey 2025 isn't held: 2026 uses the newest survey out on 2026-01-01 (2023, per the package's dates).
    assert (q1.schedule[-1].status, q1.schedule[-1].survey) == ("first", 2023)
    assert sum(q1.published[f"2025-{m:02d}"] for m in range(1, 13)) / 12 == pytest.approx(100, abs=0.01)


def test_an_item_with_no_index_anywhere_fails_the_run():
    """PY-INDEX-002: an item with no index anywhere fails the run

    Given baskets with an item (05) whose price index stops after 2014
    When the series is built
    Then a FormatError is raised
    """
    b = blocks()
    k = {key: Basket({"01": 0.5, "05": 0.5}, {"01": "normal", "05": "normal"}) for key in baskets()}
    for y in b:  # 05 has an index only for price-updating years, not after
        b[y]["05"] = flat_year(y, 100.0, 100.0) if y < 2015 else {}
    with pytest.raises(FormatError):
        index.build(None, "B", "Q1", blocks=b, baskets=k)


def test_gap_rows_use_the_rates_as_shown():
    """PY-INDEX-003: gap rows use the rates as shown

    Given the B/Q1 and B/Q5 series
    When their output rows are made
    Then there is one Q1-Q5 annual-rate gap row for 2022-12, with value text "4.0"
    """
    b, k = blocks(), baskets()
    series = [index.build(None, "B", g, blocks=b, baskets=k) for g in ("Q1", "Q5")]
    gaps = [r for r in output.rows(series)["m1_rates"] if r["unit"] == "RCH_A_GAP" and r["ref_period"] == "2022-12"]
    assert len(gaps) == 1 and gaps[0]["value_text"] == "4.0" and gaps[0]["group"] == "Q1-Q5"


def test_values_resting_on_the_original_tables_are_flagged():
    """PY-INDEX-004: values resting on ELSTAT's original tables are flagged

    Given periods on each side of the end of the original tables
    When the quality flag of each measure is read
    Then the index is "less certain" up to 2010-12, the annual rate up to 2011-12, the monthly rate up to 2011-01 and the annual average for 2011
    And each is unflagged from the next period
    """
    q = output.quality
    assert q("I25", "2010-12") == "less certain" and q("I25", "2011-01") == ""
    assert q("RCH_A", "2011-12") == "less certain" and q("RCH_A", "2012-01") == ""
    assert q("RCH_M", "2011-01") == "less certain" and q("RCH_M", "2011-02") == ""
    assert q("RCH_A_AVG", "2011") == "less certain" and q("RCH_A_AVG", "2012") == ""


def test_an_income_fifth_is_built_without_the_2010_survey():
    """PY-INDEX-005: an income fifth's series is built without the 2010 survey, the 2009 survey price-updated in its place

    Given baskets for surveys 2008 to 2024 with none for the 2010 survey's fifths
    When the B/Q1 series is built with the default rule
    Then it runs from 2009 as usual, and 2011 uses survey 2009's basket
    And that basket is price-updated from 2009, the stand-in's own year
    """
    k = baskets()
    del k[(2010, "B", "Q1")], k[(2010, "B", "Q5")]
    q1 = index.build(None, "B", "Q1", blocks=blocks(), baskets=k)
    assert q1.schedule[0].year == 2009
    entry = q1.used[2011].entry
    assert entry.survey == 2009 and entry.price_update_from == 2009


def test_the_default_prices_take_the_original_tables_before_2011(monkeypatch):
    """PY-INDEX-006: the default prices are table 07's re-issued blocks, with the original tables' blocks before 2011

    Given re-issued table 07 blocks for 2010 to 2012, and original-table blocks for 2008 to 2010
    When the default prices are put together
    Then 2008 and 2009 come from the original tables, 2011 and 2012 from the re-issue
    And 2010, in both, comes from the original tables
    """
    from traceconomics.module1 import originals

    monkeypatch.setattr(index, "cpi_blocks", lambda con, when: {y: f"reissued {y}" for y in (2010, 2011, 2012)})
    monkeypatch.setattr(originals, "blocks", lambda archive: ({y: f"original {y}" for y in (2008, 2009, 2010)}, None))
    assert index.price_blocks("con", "archive") == {
        2008: "original 2008",
        2009: "original 2009",
        2010: "original 2010",
        2011: "reissued 2011",
        2012: "reissued 2012",
    }


def test_every_published_group_is_built_on_the_same_prices_and_baskets(monkeypatch):
    """PY-INDEX-007: every published group's series is built once, all on the same prices and baskets

    Given stand-ins for the default prices, the stored baskets and the series builder
    When every series is built for one spending definition and date, then for two chosen groups only
    Then each published group is built once, in order, with that spending, date, prices and baskets
    And the prices and baskets are read once, the baskets for that spending
    And the chosen groups alone are built the second time
    """
    calls, reads = [], []
    monkeypatch.setattr(index, "price_blocks", lambda con, archive, when: reads.append(("prices", when)) or "P")
    monkeypatch.setattr(index, "load_baskets", lambda con, spending: reads.append(("baskets", spending)) or "B")
    monkeypatch.setattr(index, "build", lambda con, g, q, **kw: calls.append((g, q, kw)) or (g, q))
    got = index.build_all("con", "archive", spending="consumption", when="2026-01-01")
    assert got == list(index.PUBLISHED_GROUPS)
    assert all(
        kw == {"spending": "consumption", "when": "2026-01-01", "blocks": "P", "baskets": "B"} for _, _, kw in calls
    )
    assert reads == [("prices", "2026-01-01"), ("baskets", "consumption")]
    assert index.build_all("con", "archive", groups=[("B", "Q1"), ("all", "all")]) == [("B", "Q1"), ("all", "all")]


def test_the_stored_baskets_are_the_newest_rows_of_the_wanted_setting():
    """PY-INDEX-008: the stored baskets are each share's and tier's newest row, for the setting asked for

    Given stored weights rows: a share published twice, a share withdrawn later, a reliability tier, and rows for another spending definition and another country
    When the baskets are read for purchases in Greece
    Then each group's basket holds the newest value of each share, and its tiers
    And the withdrawn share and the other setting's rows are left out
    And the survey year is a number
    """
    import duckdb

    from traceconomics.module1.weights_used import load_baskets

    con = duckdb.connect()
    con.execute(
        'CREATE TABLE observations (dataset VARCHAR, key VARCHAR, ref_period VARCHAR, grouping VARCHAR, "group" VARCHAR, '
        "coicop18 VARCHAR, measure VARCHAR, value DOUBLE, value_text VARCHAR, geo VARCHAR, spending VARCHAR, "
        "imputed_rent VARCHAR, status VARCHAR, published_at TIMESTAMP, retrieved_at TIMESTAMP)"
    )
    old, new = "2026-01-01", "2026-06-01"

    def row(code, measure, value, text=None, *, at=new, status="final", spending="purchases", geo="GR", key=None):
        k = key or f"{spending}|{geo}|Q1|{code}|{measure}"
        return (
            "oet-local:hbs_weights",
            k,
            "2020",
            "B",
            "Q1",
            code,
            measure,
            value,
            text,
            geo,
            spending,
            "excluded",
            status,
            at,
            at,
        )

    con.executemany(
        "INSERT INTO observations VALUES (" + ", ".join("?" * 15) + ")",
        [
            row("01", "share", 0.30, at=old),
            row("01", "share", 0.25),  # the newer publication
            row("02", "share", 0.10, at=old),
            row("02", "share", 0.10, status="withdrawn"),
            row("03", "share", 0.65),
            row("01", "reliability", None, "flagged"),
            row("01", "share", 0.99, spending="consumption"),
            row("01", "share", 0.99, geo="CY"),
        ],
    )
    got = load_baskets(con, spending="purchases")
    assert list(got) == [(2020, "B", "Q1")]
    basket = got[(2020, "B", "Q1")]
    assert basket.shares == {"01": 0.25, "03": 0.65}
    assert basket.reliability == {"01": "flagged"}
