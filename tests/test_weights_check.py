"""The build's check that the newest year's weights follow rule N, on small output files."""

from datetime import date
from pathlib import Path

import duckdb
import pytest

from traceconomics.module1 import weights_check

pytestmark = pytest.mark.unit

RELEASES = {
    2023: {"available": date(2024, 10, 1)},
    2024: {"available": date(2025, 5, 7)},
    2025: {"available": date(2026, 4, 1)},
}
OPTIONS = {"spending": "purchases", "imputed_rent": "excluded", "price_source": "cpi", "tutoring": "priced"}


def write(folder: Path, weights: list[tuple], index_last: str = "2026-09", timing: str = "N") -> Path:
    """m1_weights_used rows (group, year, survey, status) for grouping B, and an index to `index_last`,
    every column text, as the outputs are written."""
    folder.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    cols = ["grouping", "group", *OPTIONS, "weights_timing", "ref_period", "survey", "weights_status"]
    con.execute("CREATE TABLE w (" + ", ".join(f'"{c}" TEXT' for c in cols) + ")")
    for group, year, survey, status in weights:
        con.execute(
            "INSERT INTO w VALUES (" + ", ".join("?" * len(cols)) + ")",
            ["B", group, *OPTIONS.values(), timing, str(year), str(survey), status],
        )
    con.execute(f"COPY w TO '{(folder / 'm1_weights_used.parquet').as_posix()}' (FORMAT parquet)")
    con.execute(
        'CREATE TABLE i AS SELECT DISTINCT grouping, "group", spending, imputed_rent, price_source, tutoring, '
        f"weights_timing, '{index_last}' AS ref_period FROM w"
    )
    con.execute(f"COPY i TO '{(folder / 'm1_index.parquet').as_posix()}' (FORMAT parquet)")
    return folder


@pytest.mark.parametrize(
    "year, held, want",
    [
        (2026, {2023, 2024, 2025}, (2025, "final")),
        (2026, {2023, 2024}, (2024, "first")),
        (2025, {2023, 2024}, (2024, "final")),
        (2025, {2023}, (2023, "first")),
        (2024, {2024}, None),
    ],
    ids=["survey y-1 held", "first estimate", "final again", "older first estimate", "nothing available"],
)
def test_rule_n_for_the_newest_year(year, held, want):
    """PY-WCHK-001: rule N, restated: final from survey y-1 if held, else the newest survey out before 1 January

    Given the surveys held and the dates their public files came out
    When the weights rule N gives for a year are worked out
    Then a held survey of the year before gives final weights
    And otherwise the newest held survey out before 1 January of the year gives a first estimate
    And a survey out later in the year can't be used, so without any the answer is none
    """
    assert weights_check.expected(year, held, RELEASES) == want


def test_outputs_that_follow_rule_n_pass(tmp_path):
    """PY-WCHK-002: outputs whose newest year follows rule N pass, and other timing rules are not judged

    Given outputs whose newest year 2026 uses survey 2024 as a first estimate, surveys 2023-2024 held
    And rows of another timing rule with other surveys
    When the weights check runs
    Then it finds no problem
    """
    folder = write(tmp_path / "m1", [("Q1", 2025, 2024, "final"), ("Q1", 2026, 2024, "first")])
    assert weights_check.check(folder, {2023, 2024}, RELEASES) == []
    other = write(tmp_path / "f", [("Q1", 2026, 2023, "final")], timing="F")
    assert weights_check.check(other, {2023, 2024}, RELEASES) == []


@pytest.mark.parametrize(
    "held, rows, index_last, problem",
    [
        (
            {2023, 2024, 2025},
            [("Q1", 2026, 2024, "first")],
            "2026-09",
            "2026: B/Q1 uses survey 2024 (first), rule N gives (2025, 'final')",
        ),
        (
            {2023, 2024},
            [("Q1", 2026, 2023, "first")],
            "2026-09",
            "2026: B/Q1 uses survey 2023 (first), rule N gives (2024, 'first')",
        ),
        (
            {2023, 2024},
            [("Q1", 2026, 2024, "final")],
            "2026-09",
            "2026: B/Q1 uses survey 2024 (final), rule N gives (2024, 'first')",
        ),
        ({2023, 2024}, [("Q1", 2026, 2024, "first")], "2027-01", "B/Q1: weights end in 2026, its index in 2027"),
    ],
    ids=["new survey missed", "old survey kept", "wrong status", "weights stop early"],
)
def test_a_wrong_switch_fails(tmp_path, held, rows, index_last, problem):
    """PY-WCHK-003: a wrong weights switch in the newest year fails the check, naming the group and what rule N gives

    Given outputs whose newest year missed a new survey, kept an older one, has the wrong status, or whose weights stop before the index does
    When the weights check runs
    Then it names the problem, with the group, the survey used and what rule N gives
    """
    assert weights_check.check(write(tmp_path / "m1", rows, index_last), held, RELEASES) == [problem]
