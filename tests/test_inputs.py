"""`check inputs`: our survey tables against the code and the files they were built from.

The archive is synthetic: the "survey files" are a few placeholder bytes under the datasets'
real names (no microdata), and the tables carry only their provenance lines.
"""

import hashlib
import json
from datetime import UTC, datetime, timedelta

import pytest
from clitools import run, setup  # noqa: F401 - fixtures

from traceconomics.archive.store import Archive
from traceconomics.local import inputs, survey_tables as st

pytestmark = pytest.mark.integration

YEAR = 2024
HBS_PUF = f"puf-hbs-{YEAR}"
SILC_PUF = f"puf-statistics-on-income-and-living-conditions-silc-{YEAR}"
T0 = datetime(2026, 11, 1, tzinfo=UTC)


class Synthetic:
    """An archive holding one year's survey files, table 1.03, EU-SILC table and six HBS tables,
    each table's provenance naming the current code and the archive's newest inputs."""

    def __init__(self, root):
        self.archive = Archive(root)
        self.clock = T0
        self.put("elstat", HBS_PUF, b"placeholder for the survey file")
        self.put("elstat", SILC_PUF, b"placeholder for the EU-SILC file")
        self.put("elstat", "doc-1", b"placeholder for table 1.03", name=f"SFA05_TB_AN_00_{YEAR}_103_F_EN.xlsx")
        self.silc_table()
        self.hbs_tables()

    def put(self, source, dataset, data, name=None):
        self.clock += timedelta(minutes=1)
        extra = {"original_name": name} if name else None
        return self.archive.store_bytes(source, dataset, data, url=None, retrieved_at=self.clock, extra=extra)

    def newest(self, source, dataset):
        return f"{source}/{dataset}@{self.archive.latest(source, dataset)['sha256'][:12]}"

    def silc_table(self, **override):
        prov = {"survey": self.newest("elstat", SILC_PUF), "code_fingerprint": st.silc_fingerprint()[:16]}
        self.table(st.SILC.format(year=YEAR), prov | override)

    def hbs_provenance(self, **override):
        table_103 = self.archive.root / self.archive.latest("elstat", "doc-1")["path"]
        return {
            "survey": self.newest("elstat", HBS_PUF),
            "table_103": hashlib.sha256(table_103.read_bytes()).hexdigest()[:12],
            "mapping": st.mapping_hashes(),
            "code_fingerprint": st.weights_fingerprint()[:16],
            "tenure_target": {"silc": [self.newest("oet-local", st.SILC.format(year=YEAR))]},
        } | override

    def hbs_tables(self, **override):
        prov = self.hbs_provenance(**override)
        for name in st.HBS_TABLES:
            self.table(name.format(year=YEAR), prov)

    def table(self, dataset, prov, rows="geo\nGR\n"):
        text = f"# a table\n# provenance: {json.dumps(prov, sort_keys=True)}\n{rows}"
        self.put("oet-local", dataset, text.encode("utf-8"))


@pytest.fixture
def synthetic(tmp_path):
    return Synthetic(tmp_path / "archive")


def check(synthetic):
    return inputs.check(Archive(synthetic.archive.root))


def test_tables_built_from_the_newest_inputs_match(synthetic):
    """PY-INPUTS-001: tables built by this code from the archive's newest inputs pass

    Given a synthetic archive with one year's survey files, table 1.03, EU-SILC table and six survey tables
    And every table names the current code and the archive's newest inputs
    When the inputs are checked
    Then the check passes with no problems and no fix to suggest
    And it reports the EU-SILC year and the survey year as matching
    """
    r = check(synthetic)
    assert r.ok and r.problems == [] and r.fix is None
    assert r.checked == [f"EU-SILC {YEAR}: matches", f"household budget survey {YEAR}: all 6 tables match"]


def test_a_code_change_makes_the_survey_tables_stale(synthetic, monkeypatch):
    """PY-INPUTS-002: a change to the code that shapes the survey tables makes them stale

    Given tables built by the code as it was
    When the code's fingerprint changes (a deploy) and the inputs are checked
    Then the check fails, naming the year and both fingerprints
    And the fix is to run `weights run`
    """
    old = st.weights_fingerprint()[:16]
    monkeypatch.setattr(st, "weights_fingerprint", lambda: "f" * 64)
    r = check(synthetic)
    assert not r.ok
    assert r.problems == [
        f"household budget survey {YEAR}: built by other code (fingerprint {old}, the code's is {'f' * 16})"
    ]
    assert r.fix == inputs.HBS_FIX


def test_a_silc_run_alone_makes_the_survey_tables_stale(synthetic):
    """PY-INPUTS-003: rebuilding the EU-SILC table makes the weights calibrated to it stale

    Given tables whose weights are calibrated to the year's EU-SILC table
    When the EU-SILC table is rebuilt (new content, same code) and the inputs are checked
    Then the EU-SILC table itself matches
    And the survey's tables are stale, naming the EU-SILC table they were built from
    And the fix is `weights run` only
    """
    synthetic.table(  # same code and survey file, new rows: a new file
        st.SILC.format(year=YEAR),
        {"survey": synthetic.newest("elstat", SILC_PUF), "code_fingerprint": st.silc_fingerprint()[:16]},
        rows="geo\nGR\nGR\n",
    )
    r = check(synthetic)
    assert f"EU-SILC {YEAR}: matches" in r.checked
    assert len(r.problems) == 1 and "built from oet-local/silc-tenure-gr-2024@" in r.problems[0]
    assert r.fix == inputs.HBS_FIX


def test_stale_silc_tables_come_first_and_ask_for_silc_run(synthetic, monkeypatch):
    """PY-INPUTS-004: stale EU-SILC tables are named first, with the fix that rebuilds both

    Given tables built by the EU-SILC code as it was
    When that code's fingerprint changes and the household budget survey's code also changes
    Then the first problem is the EU-SILC table's
    And the fix is `silc run`, then `weights run`
    """
    monkeypatch.setattr(st, "silc_fingerprint", lambda: "a" * 64)
    monkeypatch.setattr(st, "weights_fingerprint", lambda: "b" * 64)
    r = check(synthetic)
    assert r.problems[0].startswith(f"EU-SILC {YEAR} (silc-tenure-gr-{YEAR}): built by other code")
    assert any(p.startswith("household budget survey") for p in r.problems)
    assert r.fix == inputs.SILC_FIX


def test_a_reissued_survey_file_makes_its_tables_stale(synthetic):
    """PY-INPUTS-005: a newer copy of a survey file makes the tables built from it stale

    Given tables built from the archived survey files
    When ELSTAT's files are archived again with new content and the inputs are checked
    Then both the EU-SILC table and the survey's tables are stale, each naming the copy it was built from
    """
    synthetic.put("elstat", HBS_PUF, b"placeholder for a re-issued survey file")
    synthetic.put("elstat", SILC_PUF, b"placeholder for a re-issued EU-SILC file")
    r = check(synthetic)
    assert any(p.startswith(f"EU-SILC {YEAR}") and f"built from elstat/{SILC_PUF}@" in p for p in r.problems)
    assert any(p.startswith("household budget survey") and f"built from elstat/{HBS_PUF}@" in p for p in r.problems)
    assert r.fix == inputs.SILC_FIX


def test_a_newer_table_103_makes_the_survey_tables_stale(synthetic):
    """PY-INPUTS-006: a newer ELSTAT table 1.03 for the year makes the survey's tables stale

    Given tables checked against the archived table 1.03
    When a newer table 1.03 for the same year is archived and the inputs are checked
    Then the survey's tables are stale: checked against an older table 1.03
    """
    synthetic.put(
        "elstat", "doc-2", b"placeholder for a revised table 1.03", name=f"SFA05_TB_AN_00_{YEAR}_103_F_EN.xls"
    )
    r = check(synthetic)
    assert r.problems == [
        f"household budget survey {YEAR}: checked against an older table 1.03 than the archive's newest"
    ]


def test_tables_from_two_runs_are_stale(synthetic):
    """PY-INPUTS-007: a year whose six tables come from different runs fails

    Given a year's six tables from one run
    When one of them is written again with another run's provenance (as a build would see during a `weights run`)
    Then the check fails, saying the tables come from different runs
    """
    other = synthetic.hbs_provenance(replicates=7)
    synthetic.table(st.RENT.format(year=YEAR), other)
    r = check(synthetic)
    assert r.problems == [
        f"household budget survey {YEAR}: its 6 tables come from different runs (read during a `weights run`?)"
    ]


def test_changed_mapping_tables_make_the_survey_tables_stale(synthetic, monkeypatch):
    """PY-INPUTS-008: changed mapping tables make the survey's tables stale

    Given tables built with the mapping tables as they were
    When the mapping tables' hashes change and the inputs are checked
    Then the survey's tables are stale: built with other mapping tables
    """
    monkeypatch.setattr(st, "mapping_hashes", lambda: {"old_to_v1.csv": "0" * 12})
    r = check(synthetic)
    assert r.problems == [f"household budget survey {YEAR}: built with other mapping tables"]


def test_an_archive_without_survey_files_or_tables_passes_with_nothing_checked(tmp_path):
    """PY-INPUTS-009: an archive with no survey files and no tables passes, with nothing checked

    Given an empty archive, as on a machine without microdata
    When the inputs are checked
    Then the check passes with no problems and nothing reported as checked
    """
    r = inputs.check(Archive(tmp_path / "archive"))
    assert r.ok and r.checked == [] and r.problems == []


def test_a_survey_file_without_tables_is_stale(tmp_path):
    """PY-INPUTS-010: an archived survey file with no tables built from it fails

    Given an archive holding a survey file and an EU-SILC file but no tables
    When the inputs are checked
    Then the EU-SILC year and the survey year are both stale, each for a missing table
    And the fix is `silc run`, then `weights run`
    """
    a = Archive(tmp_path / "archive")
    for dataset in (HBS_PUF, SILC_PUF):
        a.store_bytes("elstat", dataset, b"placeholder", url=None, retrieved_at=T0)
    r = inputs.check(a)
    assert r.problems[0] == f"EU-SILC {YEAR} (silc-tenure-gr-{YEAR}): no table, though the survey file is archived"
    assert r.problems[1].startswith(
        f"household budget survey {YEAR}: no table or no provenance line: hbs-weights-gr-{YEAR}"
    )
    assert r.fix == inputs.SILC_FIX


def test_tables_from_before_the_tenure_calibration_are_stale(synthetic):
    """PY-INPUTS-011: tables whose provenance names no EU-SILC table are stale

    Given a year's six tables written by code from before the weights were calibrated to EU-SILC
    When the inputs are checked
    Then the survey's tables are stale: built before the calibration
    """
    synthetic.hbs_tables(tenure_target={})
    r = check(synthetic)
    assert r.problems == [
        f"household budget survey {YEAR}: built before the weights were calibrated to EU-SILC's tenure split"
    ]


def test_check_inputs_passes_on_the_command_line(synthetic, setup, run):
    """PY-INPUTS-012: `check inputs` exits 0 and says so when the tables match

    Given the command line's configured archive holding tables that match their inputs
    When `check inputs` runs
    Then it exits 0, lists the year as ok and says the inputs match
    """
    synthetic.archive.root.rename(setup.cfg.archive_dir)
    code, out = run("check", "inputs")
    assert code == 0 and f"ok    household budget survey {YEAR}" in out and "Inputs match." in out


def test_check_inputs_fails_on_the_command_line_with_the_fix(synthetic, setup, run, monkeypatch):
    """PY-INPUTS-013: `check inputs` exits 1 and prints the fix when the tables are stale

    Given the command line's configured archive holding tables built by the code as it was
    When the code's fingerprint changes and `check inputs` runs
    Then it exits 1, marks the year STALE and prints the command that rebuilds the tables
    """
    synthetic.archive.root.rename(setup.cfg.archive_dir)
    monkeypatch.setattr(st, "weights_fingerprint", lambda: "f" * 64)
    code, out = run("check", "inputs")
    assert code == 1 and f"STALE household budget survey {YEAR}" in out and inputs.HBS_FIX in out
