"""The survey checks that put published figures back (hospital services) or compare with them (V2),
on a made-up survey of ten households: the real grouping, mapping and shares code runs on it; only
reading the survey file and the published table is replaced. Never real microdata."""

from dataclasses import replace
from datetime import UTC, datetime

import pytest

pd = pytest.importorskip("pandas")
np = pytest.importorskip("numpy")

from traceconomics.archive.store import Archive  # noqa: E402
from traceconomics.checks import FormatError  # noqa: E402
from traceconomics.local import hospital_check as hc, mapping, mapping_check as mc, puf, v2  # noqa: E402
from traceconomics.local.puf import Survey, classification  # noqa: E402
from traceconomics.module1 import index  # noqa: E402
from traceconomics.module1.weights_used import Basket  # noqa: E402
from traceconomics.sources.elstat import hbs_tables  # noqa: E402
from traceconomics.sources.elstat.hbs_tables import ALL, Table103  # noqa: E402

pytestmark = pytest.mark.unit

INCOME = [6000, 9000, 12000, 15000, 18000, 24000, 30000, 36000, 48000, 60000]  # euros a year
BANDS = ["up to 750", "751-1100", "1101-1800", "1801-2800", "2801 and over"]  # euros a month
SIZES = ["1 member", "2 members", "3 members and over"]
HOSPITAL = dict(zip(BANDS, (10.0, 20.0, 30.0, 40.0, 50.0), strict=True))  # euros a month


# Rent paid, imputed rent and housed free, in each era's code list (tenure is read from them).
RENT_CODES = {
    "hbs-gr-2008": ("04111", "04211", "04221"),
    "ecoicop1": ("04110", "04210", "04220"),
    "coicop2018": ("04110", "04210", "04220"),
}


def survey(year=2010, n=10, food=1.0, repairs=0.0):
    """n one-person households in the year's code list: food rising with income (times `food`), odd
    ones renting, even ones owning, some transport, one weight each; two strata of areas. With
    `repairs`, each household also spends that on audio-visual repairs, which ECOICOP v1 holds in
    one code (09150) and COICOP 2018 splits between recreation (09410) and communication (08350)."""
    era = classification(year)
    incomes = INCOME if n == len(INCOME) else [6000 + 1200 * i for i in range(n)]
    h = pd.DataFrame(
        {
            "hh": [str(i) for i in range(n)],
            "weight": 1.0,
            "region": "EL3",
            "stratum": ["1" if i < n // 2 else "2" for i in range(n)],
            "cluster": [f"{'1' if i < n // 2 else '2'}-{(i % (n // 2)) // max(2, n // 10)}" for i in range(n)],
            "money_income": [float(x) for x in incomes],
            "total_income": [float(x) for x in incomes],
            "main_income_source": "1",
        }
    )
    rent, imputed, free = RENT_CODES[era]
    leaf = pd.DataFrame(
        {
            "01111": [(100.0 + 10 * i) * food for i in range(n)],
            rent: [300.0 * (i % 2) for i in range(n)],
            imputed: [400.0 * (1 - i % 2) for i in range(n)],
            free: 0.0,
            "07221": [50.0 + i for i in range(n)],
        }
    )
    if repairs and era == "ecoicop1":
        leaf["09150"] = repairs
    elif repairs and era == "coicop2018":
        leaf["08350"], leaf["09410"] = repairs / 2, repairs / 2
    s = mapping.with_parents(leaf)
    persons = pd.DataFrame({"hh": h.hh, "age": 40, "relation": "1", "activity": "1"})
    return Survey(
        year=year,
        classification=classification(year),
        households=h,
        persons=persons,
        spending=s,
        purchases=s.copy(),
        design="full",
        source_sha256="0" * 64,
    )


def table(year=2010, by="income"):
    """A published table 1.03 for the survey: its bands' hospital averages and all households' purchases."""
    groups = BANDS if by == "income" else SIZES
    t = Table103(year, [ALL, *groups], households={ALL: 10.0} | {g: 2.0 for g in groups})
    s = survey(year)
    for code in ("00", "01", "011", "0111", "01111"):
        col = s.purchases["01111"] if code != "00" else s.purchases[["01", "04", "07"]].sum(axis=1)
        t.purchases[code] = {ALL: round(float(col.mean() / 12), 4)}
    t.purchases["07242"] = {ALL: 5.0}
    t.purchases[hc.HOSPITAL_OLD] = HOSPITAL if by == "income" else {g: 25.0 for g in SIZES}
    return t


def store_silc(archive, year, renter, owner, rent_free):
    """An EU-SILC tenure table in the archive, as `traceconomics silc run` writes it: households weighted by tenure."""
    from traceconomics.local import silc, weights

    rows = [
        {
            "geo": "GR",
            "ref_year": year,
            "tenure": t,
            "n_households": "100",
            "households_weighted": v,
            "people_weighted": v,
            "rent_paid_eur": 0.0,
            "source_version": "made up",
        }
        for t, v in (
            ("all", renter + owner + rent_free),
            ("owner", owner),
            ("renter", renter),
            ("rent_free", rent_free),
        )
    ]
    archive.store_bytes(
        "oet-local",
        silc.OUT.format(year=year),
        weights.to_csv(pd.DataFrame(rows)[silc.COLUMNS], ["made up"]),
        url=None,
        retrieved_at=datetime(2026, 1, 1, tzinfo=UTC),
        ext=".csv",
        kind="local",
    )


AS_SURVEYED = {"renter": 0.5, "owner": 0.5, "rent_free": 0.0}  # the made-up surveys' own split


@pytest.fixture
def files(monkeypatch):
    """Reading a year's survey or table gives the made-up ones for that year; the tenure target is
    the made-up surveys' own split, so calibration leaves their weights as they are."""
    from traceconomics.local import calibration

    monkeypatch.setattr(
        calibration, "target", lambda archive, year: calibration.Target(AS_SURVEYED, "test", AS_SURVEYED, ())
    )
    monkeypatch.setattr(puf, "read", lambda archive, year: survey(year))
    monkeypatch.setattr(hbs_tables, "parse", lambda path, year: table(year, v2.BANDED.get(year, "income")))
    monkeypatch.setattr(v2, "archived_tables", lambda archive: {y: f"t{y}" for y in range(2008, 2025)})


# -- hospital services -----------------------------------------------------------------------------


def test_each_household_gets_its_bands_hospital_spending():
    """PY-HOSP-001: each household gets its income band's published hospital spending

    Given ten households with monthly money incomes from 500 to 5,000 euros
    And a 2010 table whose bands spend 10, 20, 30, 40 and 50 euros a month on hospitals
    When each household's hospital spending is worked out
    Then each gets its band's monthly average times twelve, a band including its top
    And the bands are named as income bands, exact for 2010
    And for 2009, a year whose bands can't be rebuilt exactly, they are labelled approximate
    """
    euros, how = hc.with_hospital(survey(), table())
    assert euros.tolist() == [120.0, 120.0, 240.0, 360.0, 360.0, 480.0, 480.0, 600.0, 600.0, 600.0]
    assert how == "income bands"
    assert hc.with_hospital(survey(2009), table(2009))[1] == "income bands, approximate"


def test_hospital_spending_is_put_back_into_the_baskets(files):
    """PY-HOSP-002: the hospital spending is put back into each requested group's basket

    Given the made-up 2010 and 2011 surveys and tables
    When the baskets with hospital services are built for quintile 1 and all households
    Then only those two groups' baskets are returned, keyed by survey year
    But not the 2010 survey's quintile, since that survey's incomes can't rank households
    And in each the hospital code 06310 carries all of division 06
    And hospitals are 3,960 of 9,455 euros of purchases, worked out by hand: 0.4188
    """
    out, how, share = hc.baskets_with_hospital(None, 2010, {("B", "Q1"), ("all", "all")})
    assert set(out) == {(2010, "all", "all")} and how == "income bands"
    assert set(hc.baskets_with_hospital(None, 2011, {("B", "Q1"), ("all", "all")})[0]) == {
        (2011, "B", "Q1"),
        (2011, "all", "all"),
    }
    for b in out.values():
        assert b.shares["06310"] == pytest.approx(b.shares["06"]) and b.shares["06"] > 0
    assert share == pytest.approx(3960 / 9455)


def test_the_hospital_check_reports_each_groups_change(files, monkeypatch):
    """PY-HOSP-003: the hospital check reports each survey's share and each group's change in rates

    Given the made-up surveys and tables for 2008-2014 (2013 banded by household size)
    And a series builder whose rate in a year is ten times the basket's health share the year before
    When the hospital check is run for quintiles 1 and 5
    Then every survey 2008-2014 is reported with its hospital share and how its bands were made
    And each group's change is ten times its health share with hospitals put back, through 2016 only
    But 2011, whose survey (2010) has no quintiles rebuilt, doesn't move
    And the gap's change is quintile 1's change minus quintile 5's
    """
    monkeypatch.setattr(index, "price_blocks", lambda con, archive: {})
    monkeypatch.setattr(
        hc,
        "load_baskets",
        lambda con, spending: {
            (y, g, q): Basket({"01": 1.0, "06": 0.0}, {})
            for y in range(2008, 2019)
            for g, q in (("B", "Q1"), ("B", "Q5"))
        },
    )

    def build(con, grouping, label, *, blocks, baskets):
        rates = {y + 1: 10 * baskets[(y, grouping, label)].shares.get("06", 0.0) for y in range(2008, 2019)}
        return type("S", (), {"annual_average_rates": lambda self: rates})()

    monkeypatch.setattr(index, "build", build)
    r = hc.run(None, "con", groups_wanted=[("B", "Q1"), ("B", "Q5")])
    assert list(r["surveys"]) == list(range(2008, 2015))
    assert r["surveys"][2013]["bands"] == "size bands" and r["surveys"][2008]["bands"] == "income bands, approximate"
    q1, q5 = r["series"]["B/Q1"], r["series"]["B/Q5"]
    assert sorted(q1) == list(range(2009, 2017)) and all(v > 0 for y, v in q1.items() if y <= 2015 and y != 2011)
    assert q1[2011] == q1[2016] == 0.0
    assert r["gap_change"][2011] == pytest.approx(q1[2011] - q5[2011], abs=0.002)


# -- V2 --------------------------------------------------------------------------------------------


def test_v2_finds_the_newest_english_table_of_each_year(tmp_path):
    """PY-HBS-006: V2 finds the newest archived English table 1.03 of each survey year

    Given an archive with the 2018 English table twice (retrieved in January and March), the 2024 one, a Greek one and another document
    When the archived tables are listed
    Then there is one per year, 2018 and 2024, the March copy for 2018
    And the Greek table and the other document are left out
    """
    archive = Archive(tmp_path)

    def put(doc, name, month):
        archive.store_bytes(
            "elstat",
            doc,
            f"{doc}{name}".encode(),
            url=None,
            ext=".xls",
            retrieved_at=datetime(2026, month, 1, tzinfo=UTC),
            extra={"original_name": name},
        )

    put("doc-1", "SFA05_TB_AN_00_2018_103_F_EN.xls", 1)
    put("doc-2", "SFA05_TB_AN_00_2018_103_F_EN.xls", 3)
    put("doc-3", "SFA05_TB_AN_00_2024_103_F_EN.xlsx", 2)
    put("doc-4", "SFA05_TB_AN_00_2024_103_F_GR.xlsx", 4)
    put("doc-5", "other.xls", 4)
    found = v2.archived_tables(archive)
    assert found == {
        2018: archive.root / archive.latest("elstat", "doc-2")["path"],
        2024: archive.root / archive.latest("elstat", "doc-3")["path"],
    }


def test_v2_compares_every_year_and_the_bands_where_they_can_be_rebuilt(files, monkeypatch):
    """PY-HBS-007: V2 compares all households every year, and each band where the bands can be rebuilt

    Given the made-up survey and table for 2010 (banded by income) and 2016 (bands not rebuilt)
    And item 07242 listed as missing from the survey in both years
    When V2 is run for 2010 and 2016
    Then each year's first result is for all households, with the share of purchases the survey lacks
    And 2010 adds one result per income band, 2016 none
    And for all households, five of six codes match the table to the cent and the missing item is excused
    And V2 for a year without an archived table raises an error naming it
    """
    monkeypatch.setattr(v2, "missing_items", lambda: {"07242": [2010, 2016]})
    results = v2.run(None, [2010, 2016])
    assert [(r.year, r.group) for r in results] == [(2010, ALL)] + [(2010, b) for b in BANDS] + [(2016, ALL)]
    first = results[0]
    assert first.uncovered == pytest.approx(5.0 / table().purchases["00"][ALL])
    assert (first.compared, first.matched, [e[0] for e in first.excused], first.mismatches) == (6, 5, ["07242"], [])
    monkeypatch.setattr(v2, "archived_tables", lambda archive: {})
    with pytest.raises(FileNotFoundError, match="no archived table 1.03 for 2010"):
        v2.run(None, [2010])


def test_v2_keeps_every_figure_compared_with_its_result(files, monkeypatch):
    """PY-HBS-010: V2 keeps every figure it compares, with ELSTAT's value, ours and the result

    Given the made-up survey and table for 2010, with item 07242 listed as missing from the survey
    When V2 is run for 2010
    Then all households' rows hold one row per figure compared, in code order
    And five are "matched" and the missing item is "excused", with ours as read from the survey
    And each band's result holds its own rows
    """
    monkeypatch.setattr(v2, "missing_items", lambda: {"07242": [2010]})
    results = v2.run(None, [2010])
    first = results[0]
    assert len(first.rows) == first.compared and [r[0] for r in first.rows] == sorted(r[0] for r in first.rows)
    assert sorted(r[4] for r in first.rows) == ["excused"] + ["matched"] * 5
    excused = next(r for r in first.rows if r[4] == "excused")
    assert excused[0] == "07242" and excused[:4] == first.excused[0]
    assert all(len(r.rows) == r.compared for r in results[1:])


def test_bands_by_household_size_and_their_refusals():
    """PY-HBS-008: households are banded by size in 2013, and bands that don't fit are refused

    Given the made-up survey of one-person households for 2013 and a table banded by size
    When the households are banded by size
    And banded by income against the size bands
    And banded by an unknown rule
    Then every household is in "1 member"
    And banding by income against size bands raises a FormatError naming the bands
    And the unknown rule raises a ValueError
    """
    s, t = survey(2013), table(2013, "size")
    assert set(v2.bands(s, t, "size")) == {"1 member"}
    with pytest.raises(FormatError, match="unexpected income bands"):
        v2.bands(s, t, "income")
    with pytest.raises(ValueError):
        v2.bands(s, t, "region")


def test_the_published_coefficients_of_variation_and_missing_items_are_on_file():
    """PY-HBS-009: the published coefficients of variation and the PUF's missing items are on file

    Given the package's files of published CVs and of items the public files lack
    When they are read
    Then every published CV entry names its source and gives a CV for the total ("00")
    And every missing item lists the survey years it is missing from
    And a CV check passes only when every division is within its tolerance
    """
    cvs = v2.published_cvs()
    assert cvs and all("source" in e and "00" in e["cv"] for e in cvs.values())
    missing = v2.missing_items()
    assert missing and all(isinstance(years, list) and years for years in missing.values())
    ok = v2.CVResult(2016, "full", [("00", 1.0, 1.05), ("01", 2.0, 2.1)], {"00": 0.1, "01": 0.2})
    assert ok.passed and not replace(ok, rows=[("00", 1.0, 1.5)]).passed


# -- the mapping check -----------------------------------------------------------------------------


def test_the_effective_mapping_of_each_code_list():
    """PY-MAP-011: each survey's own codes map to COICOP 2018 in one step

    Given the package's mapping tables
    When the effective table is asked for a 2016 survey (ECOICOP v1) and a 2010 survey (the 2008-2014 list)
    Then 2016's is the v1 table itself
    And 2010's goes through the bridge and the v1 table in one step
    And in both, each source code's shares add up to 1
    """
    v1, old = mc.effective_table(2016), mc.effective_table(2010)
    assert v1.equals(mapping.load(mapping.V1_TO_2018)[["from_code", "to_code", "share"]])
    assert set(old.from_code) == set(mapping.load(mapping.OLD_TO_V1).from_code)
    for t in (v1, old):
        assert np.allclose(t.groupby("from_code").share.sum(), 1.0)


def test_the_reasons_for_known_differences_are_read_by_year_pair(tmp_path, monkeypatch):
    """PY-MAP-012: the reasons for known differences after the mapping are read by year pair and code

    Given the package's file of explained differences
    And a made-up file in its place explaining code 0111 for 2023-2024
    When each is read
    Then the package's file reads as a table of year pairs (it may hold none yet)
    And the made-up one gives {"2023-2024": {"0111": its reason}}
    """
    assert isinstance(mc.explained(), dict)
    folder = tmp_path / "data"
    folder.mkdir()
    (folder / "mapping_explained.toml").write_text('["2023-2024".0111]\nreason = "bread moved"\n', encoding="utf-8")
    monkeypatch.setattr(mc.resources, "files", lambda package: folder)
    assert mc.explained() == {"2023-2024": {"0111": "bread moved"}}


def test_all_households_shares_with_and_without_standard_errors():
    """PY-MAP-013: all households' shares come with standard errors only when replicates are asked for

    Given the made-up survey of 50 households for 2023, moved to COICOP 2018
    When all households' shares are worked out without replicates
    And with 50 bootstrap replicates
    Then both give the same shares, in percent, the divisions adding up to 100
    And without replicates there are no standard errors, with them every share has one
    """
    s = mapping.to_2018(survey(2023, n=50))
    plain, boot = mc.all_households(s), mc.all_households(s, replicates=50)
    assert np.allclose(plain.share, boot.share)
    assert plain.share[plain.index.str.len() == 2].sum() == pytest.approx(100.0)
    assert plain.se.isna().all() and (boot.se > 0).all()


def test_the_mapped_year_is_compared_with_the_next_and_unexplained_mapping_effects_fail(monkeypatch):
    """PY-MAP-014: the last year in the old codes, mapped, is compared with the next, and unexplained mapping effects fail it

    Given made-up surveys of 2023 (ECOICOP v1) and 2024 (COICOP 2018), the second spending 60% more on food
    And audio-visual repairs, one code in 2023 that the mapping splits half and half between recreation and communication
    And food's rise explained, and no usual change for any code
    When the two years are compared with 50 replicates
    Then food is flagged, with its explanation
    And rent and transport are flagged as not from the mapping (no split decided them)
    And recreation and communication are flagged as decided entirely by a split, with no explanation
    And the comparison fails on those two
    """
    surveys = {2023: survey(2023, n=50, repairs=60.0), 2024: survey(2024, n=50, food=1.6, repairs=60.0)}
    monkeypatch.setattr(puf, "read", lambda archive, year: surveys[year])
    r = mc.compare(None, 2023, 2024, pd.Series(dtype=float), {"01": "food rose"}, replicates=50)
    flags = {f.code: f for f in r.flags if len(f.code) == 2}
    assert set(flags) == {"01", "04", "07", "08", "09"}
    assert flags["01"].explanation == "food rose"
    assert not flags["04"].from_mapping and not flags["07"].from_mapping
    assert flags["08"].exposure == pytest.approx(1.0) and flags["09"].from_mapping and not flags["09"].explanation
    assert r.table.loc["01", "diff"] > 0 and not r.passed


def test_the_usual_yearly_change_is_the_median_over_the_baseline_years(monkeypatch):
    """PY-MAP-015: a code's usual yearly change is its median change over the 2016-2023 surveys

    Given made-up surveys for 2016-2023 that are all the same
    And, separately, surveys whose food spending rises 10% a year
    When the usual change is worked out from each
    Then with identical surveys every code's usual change is 0
    And with rising food, food's usual change is positive
    """
    monkeypatch.setattr(puf, "read", lambda archive, year: survey(year))
    assert (mc.usual_change(None) == 0).all()
    monkeypatch.setattr(puf, "read", lambda archive, year: survey(year, food=1.1 ** (year - 2016)))
    assert mc.usual_change(None)["01"] > 0


def test_the_cpi_weights_are_compared_with_our_mapped_shares_a_year_or_two_before(monkeypatch):
    """PY-MAP-016: ELSTAT's CPI weights are compared with our mapped shares of the survey one and two years before

    Given made-up surveys that are the same every year
    And ELSTAT's division weights (per mille) for 2018 equal to our shares, and for 2019 6 per mille higher for food
    When the CPI report is made
    Then it has a row for each CPI year with the mean absolute difference per division for surveys t-1 and t-2
    And 2018's differences are 0, and 2019's are 2 per mille (6 spread over three divisions)
    """
    from storetools import store

    monkeypatch.setattr(puf, "read", lambda archive, year: survey(year))
    ours = mc.all_households(mapping.to_2018(survey(2017))).share
    ours = ours[ours.index.str.len() == 2] * 10
    rows = []
    for year, bump in ((2018, 0.0), (2019, 6.0)):
        for code, w in ours.items():
            rows.append(
                dict(
                    dataset="elstat:cpi07",
                    key=f"A,PM,{code}",
                    unit="PM",
                    coicop18=code,
                    ref_period=str(year),
                    value=w + (bump if code == "01" else 0.0),
                )
            )
    rows.append(dict(dataset="elstat:cpi07", key="A,PM,011", unit="PM", coicop18="011", ref_period="2018", value=1.0))
    report = mc.cpi_report(None, store(rows))
    assert report.cpi_year.tolist() == [2018, 2019]
    assert report["survey t-1"].tolist() == [0.0, 2.0] and report["survey t-2"].tolist() == [0.0, 2.0]


# -- the weights run -------------------------------------------------------------------------------


@pytest.fixture
def survey_2023(tmp_path, monkeypatch):
    """An archive holding a 2023 survey file (a placeholder: reading it gives the made-up survey of
    50 households), its English table 1.03 and EU-SILC's 2023 tenure table, at the survey's own
    split (half renting, half owning)."""
    archive = Archive(tmp_path)
    when = datetime(2026, 1, 1, tzinfo=UTC)
    archive.store_bytes("elstat", puf.dataset(2023), b"survey", url=None, retrieved_at=when, ext=".zip", kind="manual")
    archive.store_bytes(
        "elstat",
        "doc-1",
        b"table",
        url=None,
        retrieved_at=when,
        ext=".xls",
        extra={"original_name": "SFA05_TB_AN_00_2023_103_F_EN.xls"},
    )
    store_silc(archive, 2023, 25.0, 25.0, 0.0)  # the survey's own split: calibration changes nothing
    monkeypatch.setattr(puf, "read", lambda archive, year: survey(year, n=50))
    monkeypatch.setattr(hbs_tables, "parse", lambda path, year: table(year))
    monkeypatch.setattr(v2, "missing_items", lambda: {})
    return archive


def test_the_weights_run_archives_six_tables_once(survey_2023):
    """PY-OETLOCAL-008: the weights run archives a year's weights, groups, limits, household types, rent and spending check, once

    Given an archive with the 2023 survey (50 one-person households, incomes 6,000 to 64,800 euros a year) and its table 1.03
    When the weights run is made for 2023 with 20 replicates
    And made again with the same inputs
    Then the first run stores the six oet-local tables for 2023
    And the income limits are the midpoints between the fifths: 17,400, 29,400, 41,400 and 53,400 euros
    And the standard errors come from the full design
    And the second run finds all six unchanged
    And the run reports as many spending differences as the archived spending table marks "differs"
    And each table's header names its provenance, and counts under 20 are written as "<20"
    """
    from traceconomics.local import weights

    first = weights.run(survey_2023, [2023], replicates=20)[0]
    assert (
        first["weights"],
        first["groups"],
        first["limits"],
        first["types"],
        first["rent"],
        first["spending_check"],
    ) == ("stored",) * 6
    assert first["limits_eur"] == [17400, 29400, 41400, 53400] and first["se_design"] == "full"
    second = weights.run(survey_2023, [2023], replicates=20)[0]
    assert (
        second["weights"],
        second["groups"],
        second["limits"],
        second["types"],
        second["rent"],
        second["spending_check"],
    ) == ("unchanged",) * 6
    assert sorted(d for s, d in survey_2023.datasets() if s == "oet-local" and d.startswith("hbs-")) == [
        "hbs-groups-gr-2023",
        "hbs-hhtypes-gr-2023",
        "hbs-limits-gr-2023",
        "hbs-rent-gr-2023",
        "hbs-spending-gr-2023",
        "hbs-weights-gr-2023",
    ]
    text = (survey_2023.root / survey_2023.latest("oet-local", "hbs-groups-gr-2023")["path"]).read_text(
        encoding="utf-8"
    )
    assert '# provenance: {"code_fingerprint": ' in text and ",<20," in text
    spent = (survey_2023.root / survey_2023.latest("oet-local", "hbs-spending-gr-2023")["path"]).read_text(
        encoding="utf-8"
    )
    assert first["spending_differs"] == sum(",differs," in line for line in spent.splitlines())


def _table(archive, dataset):
    path = archive.root / archive.latest("oet-local", dataset)["path"]
    return pd.read_csv(path, comment="#", dtype={"group": str, "coicop18": str}), path.read_text(encoding="utf-8")


def test_the_weights_run_calibrates_to_eu_silcs_tenure_split(survey_2023):
    """PY-OETLOCAL-014: the weights run calibrates the households' weights to EU-SILC's tenure split, except in the comparison tables

    Given the archive above, but EU-SILC 2023 with 60% of households renting and 40% owning (the survey: half and half)
    When the weights run is made for 2023
    Then the groups table counts 30 renting and 20 owning households of 50: renters' weights x1.2, owners' x0.8
    And rent's share of all households' purchases rises, the renters' own basket staying as it was
    And the rent table, a comparison with the census, keeps ELSTAT's weights: 25 and 25
    And the provenance and the run's report give the target and the factors
    """
    from traceconomics.local import weights

    plain = weights.build(survey_2023, 2023, replicates=20)[0]
    store_silc(survey_2023, 2023, 60.0, 40.0, 0.0)
    report = weights.run(survey_2023, [2023], replicates=20)[0]
    groups, text = _table(survey_2023, "hbs-groups-gr-2023")
    weighted = groups.set_index(["grouping", "group"]).households_weighted
    assert (weighted["tenure", "renter"], weighted["tenure", "owner"], weighted["all", "all"]) == pytest.approx(
        (30, 20, 50)
    )
    assert report["tenure_factors"] == pytest.approx({"renter": 1.2, "owner": 0.8, "rent_free": 1.0})
    assert '"tenure_target": {"basis": "EU-SILC\'s split for the year"' in text and '"renter": 0.6' in text
    shares, _ = _table(survey_2023, "hbs-weights-gr-2023")

    def share(t, grouping, group, code):
        rows = t[
            (t.grouping == grouping)
            & (t.group == group)
            & (t.coicop18 == code)
            & (t.spending == "purchases")
            & (t.imputed_rent == "excluded")
        ]
        return float(rows.share.iloc[0])

    assert share(shares, "all", "all", "041") > share(plain, "all", "all", "041")
    assert share(shares, "tenure", "renter", "041") == pytest.approx(share(plain, "tenure", "renter", "041"))
    rent, _ = _table(survey_2023, "hbs-rent-gr-2023")
    assert rent.set_index("tenure").households_weighted[["renter", "owner"]].tolist() == [25, 25]


def test_the_2010_survey_gets_no_income_groups_and_no_income_limits(tmp_path, monkeypatch):
    """PY-OETLOCAL-015: the weights run builds no income-ranked groups and no income limits from the 2010 survey

    Given an archive with the 2010 survey (made up, 50 households), its table 1.03 and EU-SILC 2010
    When the weights run is made for 2010
    Then the weights and groups tables hold no group of a grouping ranked by income (A, B and the validation groups)
    But they hold the groups ranked by spending (C), tenure and all households
    And the limits file is written with no rows, its header saying why, so the store drops any earlier limits
    """
    from traceconomics.local import weights
    from traceconomics.module1.schedule import INCOME_RANKED
    from traceconomics.sources import oet_local

    archive = Archive(tmp_path)
    when = datetime(2026, 1, 1, tzinfo=UTC)
    archive.store_bytes("elstat", puf.dataset(2010), b"survey", url=None, retrieved_at=when, ext=".zip", kind="manual")
    archive.store_bytes(
        "elstat",
        "doc-1",
        b"table",
        url=None,
        retrieved_at=when,
        ext=".xls",
        extra={"original_name": "SFA05_TB_AN_00_2010_103_F_EN.xls"},
    )
    store_silc(archive, 2010, 25.0, 25.0, 0.0)
    monkeypatch.setattr(puf, "read", lambda archive, year: survey(year, n=50))
    monkeypatch.setattr(hbs_tables, "parse", lambda path, year: table(year))
    monkeypatch.setattr(v2, "missing_items", lambda: {})
    monkeypatch.setitem(weights.ELSTAT_TYPE_UNUSABLE, 2010, "the made-up survey carries no ELSTAT type")
    report = weights.run(archive, [2010], replicates=20)[0]
    for name in ("hbs-weights-gr-2010", "hbs-groups-gr-2010"):
        t, _ = _table(archive, name)
        assert not set(t.grouping) & set(INCOME_RANKED)
        assert {"C", "tenure", "all"} <= set(t.grouping)
    path = archive.root / archive.latest("oet-local", "hbs-limits-gr-2010")["path"]
    assert list(oet_local.rows(path, "oet-limits")) == [] and report["limits_eur"] == []
    assert "no income limits: the survey's incomes can't rank households" in path.read_text(encoding="utf-8")


def test_household_types_that_disagree_with_elstats_stop_the_run(survey_2023):
    """PY-OETLOCAL-009: a year whose household types disagree with ELSTAT's stops the weights run

    Given the made-up survey for 2019, a year whose ELSTAT type column should be usable, but which carries none
    When its household types are tabled
    Then a FormatError says our types agree with ELSTAT's on 0.0% of households, under 90%
    And for 2023, the known unusable year, the table is made and marked unusable with the reason
    """
    from traceconomics.local import weights
    from traceconomics.local.groups import assign

    s19 = survey(2019, n=50)
    with pytest.raises(FormatError, match=r"agree with ELSTAT's on 0.0% of households, under 90%"):
        weights.types_table(s19, assign(s19), 2019, "v")
    s23 = survey(2023, n=50)
    t = weights.types_table(s23, assign(s23), 2023, "v")
    assert t.elstat_status.str.startswith("unusable: HB074").all()


def test_the_income_limits_get_standard_errors_from_the_bootstrap():
    """PY-OETLOCAL-010: the income limits get standard errors from the bootstrap when replicates are asked for

    Given the made-up survey of 50 households for 2023
    When its income limits are tabled without replicates and with 20
    Then both give the same limits
    And only the second has a positive standard error for each limit
    """
    from traceconomics.local import weights

    s = survey(2023, n=50)
    plain, boot = weights.limits_table(s, 2023, 0, "v"), weights.limits_table(s, 2023, 20, "v")
    assert plain["limit"].tolist() == boot["limit"].tolist() == [17400, 29400, 41400, 53400]
    assert plain.se.isna().all() and (boot.se > 0).all()


# -- the error bands run ---------------------------------------------------------------------------


def _bands_inputs(monkeypatch, surveys):
    """Series for quintiles 1 and 5 of grouping B, built by the real series code from the surveys'
    own baskets and made-up prices (food rising faster than the rest), 2017-2019. The tenure target
    is the surveys' own split, so calibration leaves their weights as they are."""
    from traceconomics.local import calibration
    from traceconomics.local.groups import assign
    from traceconomics.local.shares import shares
    from traceconomics.module1 import combinations

    monkeypatch.setattr(puf, "read", lambda archive, year: surveys[year])
    monkeypatch.setattr(
        calibration, "target", lambda archive, year: calibration.Target(AS_SURVEYED, "test", AS_SURVEYED, ())
    )
    baskets, codes = {}, set()
    for year, s in surveys.items():
        t = shares(mapping.to_2018(s), assign(s), "purchases")
        t = t[t.imputed_rent == 1]
        codes |= set(t.code)
        for (g, label), part in t.groupby(["grouping", "group"]):
            baskets[(year, g, label)] = Basket(
                dict(zip(part.code, part.share, strict=True)), dict(zip(part.code, part.reliability, strict=True))
            )
    blocks = {
        y: {
            c: {
                f"{y - 1}-12": 100.0,
                **{f"{y}-{m:02d}": 100.0 + m * (0.5 if c.startswith("01") else 0.2) for m in range(1, 13)},
            }
            for c in codes
        }
        for y in range(2016, 2020)
    }

    def iterate(con, archive, only):
        for s in only:
            series = [
                index.build(
                    None,
                    g,
                    q,
                    blocks=blocks,
                    baskets=baskets,
                    first_year=2017,
                    options={k: s[k] for k in index.DEFAULT_OPTIONS},
                )
                for g, q in (("B", "Q1"), ("B", "Q5"))
            ]
            yield s, series, {"cpi": blocks, "hicp": blocks}

    monkeypatch.setattr(combinations, "iterate", iterate)
    return combinations.DEFAULT


def test_the_bands_run_archives_a_standard_error_for_every_rate(tmp_path, monkeypatch):
    """PY-BANDS-004: the bands run archives a standard error for every rate of every series and of the gap

    Given made-up surveys of 50 households for 2016-2018, each with its full sampling design
    And the default setting's series for quintiles 1 and 5, 2017-2019
    When the bands run is made with 10 replicates
    And made again
    Then the first run stores oet-local/hbs-bands-gr with 81 rows: 25 annual rates and 2 annual averages each for Q1, Q5 and the Q1-Q5 gap
    And every standard error is positive
    And no index year lacks a band, and every survey's design is full
    And the file's header records the replicates and the designs
    And the second run finds the file unchanged
    """
    from traceconomics.local import bands

    default = _bands_inputs(monkeypatch, {y: survey(y, n=50) for y in (2016, 2017, 2018)})
    archive = Archive(tmp_path)
    r = bands.run(archive, None, replicates=10, only=[default], log=lambda line: None)
    t = r["table"]
    assert r["status"] == "stored" and r["rows"] == 81
    assert t.groupby(["group", "unit"]).size().to_dict() == {
        ("Q1", "RCH_A"): 25,
        ("Q1", "RCH_A_AVG"): 2,
        ("Q5", "RCH_A"): 25,
        ("Q5", "RCH_A_AVG"): 2,
        ("Q1-Q5", "RCH_A_GAP"): 25,
        ("Q1-Q5", "RCH_A_AVG_GAP"): 2,
    }
    assert (t.se.astype(float) > 0).all()
    assert r["designs"] == {2016: "full", 2017: "full", 2018: "full"}
    assert r["unavailable_index_years"] == {"purchases/excluded/cpi/N/priced": []}
    text = (archive.root / archive.latest("oet-local", "hbs-bands-gr")["path"]).read_text(encoding="utf-8")
    assert '"replicates": 10' in text and '"designs": {"2016": "full"' in text
    assert bands.run(archive, None, replicates=10, only=[default], log=lambda line: None)["status"] == "unchanged"


def test_years_fed_by_a_survey_without_its_design_get_no_band(tmp_path, monkeypatch):
    """PY-BANDS-005: index years fed by a survey published without its sampling design get no band

    Given made-up surveys for 2016-2018, the 2017 one read from a file without primary sampling units
    When the bands run is made for the default setting
    Then the 2017 survey's design is unavailable
    And 2018, the index year it feeds, is listed as without a band
    And no annual rate of 2018 or 2019 (which compares with 2018) has a standard error
    """
    from traceconomics.local import bands

    surveys = {y: survey(y, n=50) for y in (2016, 2017, 2018)}
    surveys[2017] = replace(surveys[2017], design="no-clusters")  # as the reader marks such a file
    default = _bands_inputs(monkeypatch, surveys)
    r = bands.run(Archive(tmp_path), None, replicates=10, only=[default], log=lambda line: None)
    assert r["designs"][2017] == "unavailable"
    assert r["unavailable_index_years"] == {"purchases/excluded/cpi/N/priced": [2018]}
    years = {p[:4] for p in r["table"].ref_period}
    assert years == {"2017"}


# -- building the mapping tables -------------------------------------------------------------------


def _dotted(code):
    """ "01111" -> "01.1.1.1", as the correspondence writes codes."""
    return ".".join([code[:2], *code[2:]])


def _correspondence(links):
    """EU Vocabularies' correspondence as a CSV: srcNot (COICOP 2018), tgtNot (ECOICOP v1), dotted."""
    lines = ["srcNot,tgtNot,srcLabel"] + [f"{_dotted(v2)},{_dotted(v1)},x" for v1, v2 in links]
    return ("\n".join(lines) + "\n").encode()


@pytest.mark.integration
def test_the_mapping_tables_are_rebuilt_from_their_sources(tmp_path, monkeypatch):
    """PY-MAP-017: the mapping tables are rebuilt from the correspondence, the HICP weights and the surveys

    Given an archived correspondence holding every link of the package's ECOICOP v1 -> COICOP 2018 table, plus a class-level link
    And a store with a Greek 2025 HICP weight of 1 for every code in both classifications
    And made-up surveys for 2008-2023, and tables 1.03 whose labels match 2015's for food and diesel only
    When the mapping tables are built
    Then both tables are written, with their headers
    And every v1 code with a single link maps exactly as in the package's table
    And every source code's shares add up to 1
    And in the older list, food and diesel map to themselves (same code and label)
    And the old rent codes are split over their class's v1 subclasses by 2015 spending
    And the report counts the rows written
    """
    from traceconomics.module1 import output

    package = mapping.load(mapping.V1_TO_2018)
    archive = Archive(tmp_path / "archive")
    links = list(package[["from_code", "to_code"]].itertuples(index=False, name=None)) + [("011", "011")]
    archive.store_bytes(
        "eu-vocabularies",
        "ecoicop2-ecoicop1-correspondence",
        _correspondence(links),
        url=None,
        retrieved_at=datetime(2026, 10, 13, tzinfo=UTC),
        ext=".csv",
    )
    store_root = tmp_path / "store"
    (store_root / "observations" / "w").mkdir(parents=True)
    rows = [("eurostat:prc_hicp_inw", c, None) for c in sorted(set(package.from_code))]
    rows += [("eurostat:prc_hicp_iw", None, c) for c in sorted(set(package.to_code))]
    con = output.parquet_connection()
    con.execute(
        "CREATE TABLE o (dataset VARCHAR, key VARCHAR, geo VARCHAR, coicop VARCHAR, coicop18 VARCHAR, "
        "ref_period VARCHAR, value DOUBLE, status VARCHAR, published_at TIMESTAMP, retrieved_at TIMESTAMP)"
    )
    con.executemany(
        "INSERT INTO o VALUES (?, ?, 'GR', ?, ?, '2025', 1.0, 'final', TIMESTAMP '2026-01-01', TIMESTAMP '2026-01-01')",
        [(d, f"{d}:{a or b}", a, b) for d, a, b in rows],
    )
    con.execute(f"COPY o TO '{(store_root / 'observations' / 'w' / 'w.parquet').as_posix()}' (FORMAT parquet)")
    labels = {
        "01111": "Rice",
        "07221": "Diesel",
        "04111": "Rent",
        "04211": "Own home",
        "04221": "Housed free",
        "04110": "Actual rentals",
        "04210": "Imputed rentals",
        "04220": "Other imputed rentals",
    }
    monkeypatch.setattr(puf, "read", lambda archive, year: survey(year))
    monkeypatch.setattr(v2, "archived_tables", lambda archive: {y: tmp_path / f"t{y}" for y in range(2008, 2024)})
    for y in range(2008, 2024):
        (tmp_path / f"t{y}").write_bytes(b"table")
    monkeypatch.setattr(hbs_tables, "parse", lambda path, year: Table103(year, [ALL], labels=labels))
    out = tmp_path / "out"
    out.mkdir()
    report = mapping.build(archive, store_root, out)

    def read(name):
        return pd.read_csv(out / name, comment="#", dtype={"from_code": str, "to_code": str})

    v1, old = read(mapping.V1_TO_2018), read(mapping.OLD_TO_V1)
    assert (out / mapping.V1_TO_2018).read_text(encoding="utf-8").startswith("# ECOICOP v1 subclass -> COICOP 2018")
    single = package.groupby("from_code").filter(lambda g: len(g) == 1)
    rebuilt = v1[v1.from_code.isin(single.from_code)]
    assert sorted(rebuilt[["from_code", "to_code"]].itertuples(index=False, name=None)) == sorted(
        single[["from_code", "to_code"]].itertuples(index=False, name=None)
    )
    for t in (v1, old):
        assert np.allclose(t.groupby("from_code").share.sum(), 1.0)
    pairs = {(r.from_code, r.to_code): r.method for r in old.itertuples()}
    assert pairs[("01111", "01111")] == pairs[("07221", "07221")] == "same code and label"
    assert pairs[("04111", "04110")].startswith("class 0411 split by 2015 spending")
    assert (report["v1_rows"], report["old_rows"]) == (len(v1), len(old))


def test_a_correspondence_file_that_isnt_one_is_refused(tmp_path):
    """PY-MAP-018: a correspondence file without its columns or with too few subclass links is refused

    Given a CSV without the srcNot column, and one with only two subclass links
    When each is read as the correspondence
    Then the first is refused for the missing column
    And the second for having only 2 subclass links
    And building the tables without an archived correspondence is refused, naming the dataset
    """
    (tmp_path / "a.csv").write_text("tgtNot\n01.1.1.1\n", encoding="utf-8")
    with pytest.raises(FormatError, match="no column srcNot"):
        mapping.correspondence(tmp_path / "a.csv")
    (tmp_path / "b.csv").write_bytes(_correspondence([("01111", "01111"), ("01112", "01112")]))
    with pytest.raises(FormatError, match="only 2 subclass links"):
        mapping.correspondence(tmp_path / "b.csv")
    with pytest.raises(FormatError, match="eu-vocabularies/ecoicop2-ecoicop1-correspondence"):
        mapping.build(Archive(tmp_path / "archive"), tmp_path, tmp_path)
