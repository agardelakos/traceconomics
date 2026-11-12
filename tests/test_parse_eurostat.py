import gzip
from pathlib import Path

import duckdb
import pytest

from traceconomics import catalog
from traceconomics.checks import FormatError
from traceconomics.sources.eurostat import parse

pytestmark = pytest.mark.unit

FIX = Path(__file__).parent / "fixtures"
SPECS = {k: v for k, v in catalog.datasets().items() if v.format == "eurostat-tsv"}


@pytest.fixture
def con():
    c = duckdb.connect()
    yield c
    c.close()


def rows(con, sql):
    return con.execute(sql).fetchall()


@pytest.mark.parametrize("dataset_id", sorted(SPECS))
def test_every_dataset_fixture_parses(con, dataset_id):
    """PY-EUROSTAT-001: every Eurostat-format TSV dataset's fixture parses

    Given the trimmed fixture of a dataset in Eurostat's TSV format the catalog lists (Eurostat's, or DG EMPL's on the same API)
    When it is parsed
    Then it gives at least one row and one series
    And Greece is coded GR, never EL
    And where the dataset has a COICOP dimension, TOTAL is present and no code keeps the "CP" prefix
    """
    spec = SPECS[dataset_id]
    r = parse.parse(con, FIX / f"{spec.source}_{spec.name}.tsv.gz", spec)
    assert r.rows > 0 and r.series > 0
    geos = {g for (g,) in rows(con, "SELECT DISTINCT geo FROM parsed")}
    assert "GR" in geos and "EL" not in geos
    if spec.coicop:
        codes = {c for (c,) in rows(con, f"SELECT DISTINCT {spec.coicop} FROM parsed")}
        assert "TOTAL" in codes and not any(c.startswith("CP") for c in codes)


def test_income_limits_parse_with_their_units(con):
    """PY-EUROSTAT-002: the EU-SILC income limits parse with their units

    Given the ilc_di01 fixture
    When it is parsed
    Then Greece's 2025 first-quintile top cut-off is 7110 in EUR and national currency, and 8272 in PPS
    """
    parse.parse(con, FIX / "eurostat_ilc_di01.tsv.gz", SPECS["eurostat:ilc_di01"])
    got = dict(
        rows(
            con,
            """SELECT unit, value FROM parsed
        WHERE geo = 'GR' AND quant_inc = 'QU1' AND statinfo = 'TC' AND ref_period = '2025'""",
        )
    )
    assert got == {"EUR": 7110.0, "NAC": 7110.0, "PPS": 8272.0}


def test_values_kept_as_published(con):
    """PY-EUROSTAT-003: values are kept as published

    Given the HICP monthly index fixture
    When it is parsed
    Then Greece's 2026-09 all-items index has text "106.10", value 106.1 and no flags
    """
    parse.parse(con, FIX / "eurostat_prc_hicp_minr.tsv.gz", SPECS["eurostat:prc_hicp_minr"])
    ((text, value, flags),) = rows(
        con,
        """SELECT value_text, value, flags FROM parsed
        WHERE geo = 'GR' AND unit = 'I25' AND coicop18 = 'TOTAL' AND ref_period = '2026-09'""",
    )
    assert (text, value, flags) == ("106.10", 106.1, None)  # the trailing zero survives in value_text


def test_weights(con):
    """PY-EUROSTAT-004: the item weights parse

    Given the HICP item weights fixture
    When it is parsed
    Then Greece's 2026 all-items weight is 1000.0
    """
    parse.parse(con, FIX / "eurostat_prc_hicp_iw.tsv.gz", SPECS["eurostat:prc_hicp_iw"])
    assert rows(con, "SELECT value FROM parsed WHERE geo='GR' AND coicop18='TOTAL' AND ref_period='2026'") == [
        (1000.0,)
    ]


def test_flagged_empty_cell_is_kept_without_a_value(con):
    """PY-EUROSTAT-005: a flagged empty cell is kept without a value

    Given the HICP monthly index fixture
    When it is parsed
    Then there are rows without a value
    And every one of them carries a flag
    """
    parse.parse(con, FIX / "eurostat_prc_hicp_minr.tsv.gz", SPECS["eurostat:prc_hicp_minr"])
    flagged = rows(con, "SELECT flags FROM parsed WHERE value IS NULL")
    assert flagged and all(f for (f,) in flagged)


def test_release_dimension(con):
    """PY-EUROSTAT-006: the release dimension is read

    Given the HICP flash estimate fixture
    When it is parsed
    Then its releases are FIN and FLS
    """
    parse.parse(con, FIX / "eurostat_prc_hicp_fpd.tsv.gz", SPECS["eurostat:prc_hicp_fpd"])
    assert {r for (r,) in rows(con, "SELECT DISTINCT release FROM parsed")} == {"FIN", "FLS"}


# -- files that must be refused ----------------------------------------------


def write_gz(path: Path, text: str) -> Path:
    path.write_bytes(gzip.compress(text.encode("utf-8")))
    return path


HEAD = "freq,coicop18,statinfo,geo\\TIME_PERIOD\t2025 \t2026 \n"


def test_wrong_dimensions_are_refused(con):
    """PY-EUROSTAT-007: a file with the wrong dimensions is refused

    Given the item weights fixture
    When it is parsed as the monthly index dataset
    Then a FormatError about the "key dimensions" is raised
    """
    with pytest.raises(FormatError, match="key dimensions"):
        parse.parse(con, FIX / "eurostat_prc_hicp_iw.tsv.gz", SPECS["eurostat:prc_hicp_minr"])


@pytest.mark.parametrize(
    "body,message",
    [
        ("A,CP01,IW,EL\t1.0 \t2.0 xq\n", "unknown observation flags"),
        ("A,CP01,IW,EL\t1.0 \tabc \n", "aren't numbers"),
        ("A,CP01,IW,ZZZ\t1.0 \t2.0 \n", "unknown country codes"),
        ("A,CP01,IW,EL\t1.0 \t2.0 \nA,CP01,IW,EL\t1.0 \t2.0 \n", "appear twice"),
    ],
)
def test_surprises_are_refused(con, tmp_path, body, message):
    """PY-EUROSTAT-008: surprises in a file are refused

    Given a made-up weights file with one surprise: an unknown flag, a value that isn't a number, an unknown country code or a series that appears twice
    When it is parsed
    Then a FormatError naming that surprise is raised
    """
    f = write_gz(tmp_path / "bad.tsv.gz", HEAD + body)
    with pytest.raises(FormatError, match=message):
        parse.parse(con, f, SPECS["eurostat:prc_hicp_iw"])


def test_unexpected_period_column_is_refused(con, tmp_path):
    """PY-EUROSTAT-009: an unexpected period column is refused

    Given a made-up annual weights file with a monthly period column
    When it is parsed
    Then a FormatError about the "period columns" is raised
    """
    f = write_gz(tmp_path / "bad.tsv.gz", "freq,coicop18,statinfo,geo\\TIME_PERIOD\t2025-01 \nA,CP01,IW,EL\t1.0 \n")
    with pytest.raises(FormatError, match="period columns"):
        parse.parse(con, f, SPECS["eurostat:prc_hicp_iw"])


def test_capital_dimension_names_are_read_like_lower_case(con, tmp_path):
    """PY-EUROSTAT-010: a header with capital dimension names, as DG EMPL writes them, is read like Eurostat's

    Given a made-up file in DG EMPL's form: key dimensions in capitals, Greece coded EL, and a cell flagged z (not applicable)
    When it is parsed as the registered-unemployed dataset
    Then it parses, with its dimensions as lower-case columns
    And Greece is coded GR
    And the flagged cell is kept without a value
    """
    f = write_gz(
        tmp_path / "lmp.tsv.gz",
        "FREQ,UNIT,STK_FLOW,REGIS_ES,AGE,SEX,GEO\\TIME_PERIOD\t2023 \t2024 \n"
        "A,NR,STK,REG_UNE,TOTAL,T,EL\t954795 \t896099 \n"
        "A,NR,STK,REG_OTH,TOTAL,T,EL\t: z\t12 \n",
    )
    parse.parse(con, f, SPECS["ec-empl:lmp_rjru"])
    assert rows(con, "SELECT geo, regis_es, ref_period, value FROM parsed WHERE value IS NOT NULL ORDER BY ALL") == [
        ("GR", "REG_OTH", "2024", 12.0),
        ("GR", "REG_UNE", "2023", 954795.0),
        ("GR", "REG_UNE", "2024", 896099.0),
    ]
    assert rows(con, "SELECT flags FROM parsed WHERE value IS NULL") == [("z",)]


def test_regions_are_accepted_only_where_declared(con, tmp_path):
    """PY-EUROSTAT-011: NUTS regions are accepted only in a dataset declared with regions

    Given a made-up census file with Greece's total (EL), a Greek region (EL30) and a cell flagged @N (not for publication)
    When it is parsed as the 2011 census table, declared with regions
    Then Greece's total is coded GR and the region keeps its NUTS code EL30
    And the same rows in a dataset without regions are refused as unknown country codes
    """
    body = (
        "freq,hhcomp,tenure,unit,geo\\TIME_PERIOD\t2011 \n"
        "A,TOTAL,RENT,NR,EL\t896090 \nA,TOTAL,RENT,NR,EL30\t412000 \nA,TOTAL,OTH,NR,EL30\t: @N\n"
    )
    parse.parse(con, write_gz(tmp_path / "c.tsv.gz", body), SPECS["eurostat:cens_11htts_r2"])
    assert rows(con, "SELECT DISTINCT geo FROM parsed ORDER BY geo") == [("EL30",), ("GR",)]
    other = "freq,coicop18,statinfo,geo\\TIME_PERIOD\t2025 \nA,CP01,IW,EL30\t1.0 \n"
    with pytest.raises(FormatError, match="unknown country codes"):
        parse.parse(con, write_gz(tmp_path / "w.tsv.gz", other), SPECS["eurostat:prc_hicp_iw"])


class _FetchContext:
    """Just enough of a run context for `check_and_fetch`: an archive that records what it is told,
    an HTTP client that answers with given bytes or an error, and the run's lists."""

    def __init__(self, answer, tmp_path):
        from types import SimpleNamespace

        self.dry_run, self.failures, self.planned, self.logged, self.fetched = False, [], [], [], []
        self.archive = SimpleNamespace(
            new_tmp=lambda: tmp_path / "tmp",
            latest=lambda source, dataset: None,
            log_failure=lambda *a: self.logged.append(a),
        )
        self.http = SimpleNamespace(get_bytes=lambda url, tmp: answer(url))

    def fetch_and_store(self, *args, **kwargs):
        self.fetched.append(args)


def test_update_check_reports_a_failed_fetch_and_downloads_nothing(tmp_path):
    """PY-EUROSTAT-012: a dataflow that can't be fetched is logged as a failure and nothing is downloaded

    Given a run whose request for a dataset's dataflow fails
    When the dataset is checked for an update
    Then the failure is logged in the archive and added to the run's failures, naming the dataset
    And the dataset itself isn't downloaded
    """
    from traceconomics.sources import eurostat
    from traceconomics.sources.base import FetchError

    def fail(url):
        raise FetchError("HTTP 503")

    ctx = _FetchContext(fail, tmp_path)
    eurostat.check_and_fetch(ctx, "une_rt_a")
    assert ctx.logged and ctx.logged[0][:2] == ("eurostat", "une_rt_a")
    assert ctx.failures == ["eurostat/une_rt_a: HTTP 503"] and ctx.fetched == []


def test_update_check_refuses_a_dataflow_without_its_update_date(tmp_path):
    """PY-EUROSTAT-013: a dataflow without its "last data update" is reported, not guessed

    Given a run whose dataflow for a dataset has no UPDATE_DATA annotation
    When the dataset is checked for an update
    Then the run's failures say the format may have changed, naming the dataset
    And the dataset isn't downloaded
    """
    from traceconomics.sources import eurostat

    ctx = _FetchContext(lambda url: (200, b"<Structure><Dataflow id='une_rt_a'/></Structure>"), tmp_path)
    eurostat.check_and_fetch(ctx, "une_rt_a")
    assert ctx.failures == ["eurostat/une_rt_a: no UPDATE_DATA in the dataflow; the format may have changed"]
    assert ctx.fetched == []
