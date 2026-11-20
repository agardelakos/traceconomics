"""Whether a passing build may go live by itself: each rule on its own, without a build."""

import json

import pytest

from traceconomics import release_decision as rd

pytestmark = pytest.mark.unit

SHA = {name: name * 64 for name in "abcdef"}
PUBLISHED = {"elstat/doc-585819": [SHA["a"]], "oet-local/hbs-weights-gr-2024": [SHA["b"]]}
NEW_MONTH = {"latest_period": "2026-10", "new_values": 27, "new_periods": ["2026-10"], "revised_values": 0}


def with_file(inputs: dict, dataset: str, sha: str) -> dict:
    out = {k: list(v) for k, v in inputs.items()}
    out[dataset] = sorted({*out.get(dataset, []), sha})
    return out


def decide(**changed):
    """The decision for a data-only build (a new CPI file, same code, a new month), with some
    of its facts changed."""
    facts = {
        "production": "20261110T142123Z",
        "commit": "1e6ea563" * 5,
        "production_commit": "1e6ea563" * 5,
        "inputs": with_file(PUBLISHED, "elstat/doc-585819", SHA["c"]),
        "production_inputs": PUBLISHED,
        "changes": NEW_MONTH,
        "beyond": [],
        "served_problem": None,
    }
    return rd.decide(**{**facts, **changed})


def test_a_data_only_build_within_its_limits_is_promoted():
    """PY-DEC-001: a build whose only change is a publisher's new file, within every limit, is promoted

    Given a build with the production build's commit and own tables, one new ELSTAT file and a new month
    And no revised value, no group beyond its record, and production serving its recorded build
    When the decision is made
    Then it is promote, with no reasons, against the production build
    """
    d = decide()
    assert (d.verdict, d.reasons, d.production) == (rd.PROMOTE, [], "20261110T142123Z")


@pytest.mark.parametrize(
    "changed, reason",
    [
        ({"commit": "bd9bab0d" * 5}, "the code changed: commit bd9bab0dbd9b, production's build 1e6ea5631e6e"),
        ({"commit": None}, "a git commit is unknown"),
        ({"production_commit": None}, "a git commit is unknown"),
        (
            {"inputs": with_file(PUBLISHED, "oet-local/hbs-weights-gr-2024", SHA["d"])},
            f"our own tables changed: oet-local/hbs-weights-gr-2024 {SHA['d'][:12]}",
        ),
        ({"inputs": with_file(PUBLISHED, "oet-local/hbs-weights-gr-2025", SHA["d"])}, "a new survey year: 2025"),
        (
            {"inputs": with_file(PUBLISHED, "eurostat/prc_hicp_new", SHA["d"])},
            "datasets that production's build didn't have: eurostat/prc_hicp_new",
        ),
        (
            {"inputs": {"oet-local/hbs-weights-gr-2024": [SHA["b"]]}},
            "datasets gone since production's build: elstat/doc-585819",
        ),
        ({"inputs": PUBLISHED}, "nothing new: no archived file differs from production's build"),
        ({"inputs": None}, "an inputs record is missing"),
        ({"production_inputs": None}, "an inputs record is missing"),
        ({"changes": {**NEW_MONTH, "revised_values": 3, "largest_revision_pp": 0.1}}, "3 published values revised"),
        ({"changes": {}}, "no comparison with production's published rates"),
        ({"changes": {"first_release": True, "latest_period": "2026-10"}}, "no comparison with production's"),
        ({"beyond": ["B/Q1 2026-10: gap to all households +3.50 points, beyond its record 3.39"]}, "B/Q1 2026-10"),
        ({"served_problem": "after 0 s it still serves another build"}, "production doesn't serve its recorded"),
    ],
    ids=[
        "code changed",
        "commit unknown",
        "production commit unknown",
        "own table rebuilt",
        "new survey year",
        "new dataset",
        "dataset gone",
        "nothing new",
        "no inputs record",
        "production has no inputs record",
        "a value revised",
        "no rates to compare",
        "first release",
        "beyond a record",
        "production serves another build",
    ],
)
def test_each_reason_holds_the_build(changed, reason):
    """PY-DEC-002: each rule that fails holds the build, and says why

    Given a data-only build within its limits
    When one fact changes: the code, an unknown commit, a rebuilt own table, a new survey year, a new or gone dataset, nothing new, a missing inputs record, a revised value, no rates to compare, a group beyond its record, or production serving another build than its record says
    Then the decision is hold
    And its reasons name that rule
    """
    d = decide(**changed)
    assert d.verdict == rd.HOLD
    assert any(reason in r for r in d.reasons), d.reasons


def test_without_a_production_build_nothing_is_promoted():
    """PY-DEC-003: with no production build on record, the build holds

    Given no build on production to compare with
    When the decision is made
    Then it is hold, saying production serves no build on record
    """
    d = decide(production=None)
    assert d.verdict == rd.HOLD and d.reasons == ["production serves no build on record to compare with"]


def rows(series: dict[tuple[str, str], dict[str, float]]) -> list[tuple]:
    return [(g, q, p, v) for (g, q), months in series.items() for p, v in months.items()]


ALL = {"2026-07": 3.0, "2026-08": 3.0, "2026-09": 3.0}
# Q1's gap to all households: 0.5, 1.0, 0.7: its record gap is 1.0, its record monthly move 0.5.
Q1 = {"2026-07": 3.5, "2026-08": 4.0, "2026-09": 3.7}


@pytest.mark.parametrize(
    "october, expected",
    [
        (3.9, []),  # gap 0.9, move +0.2
        (4.0, []),  # gap 1.0: the record itself, computed the same way
        (4.01, ["B/Q1 2026-10: gap to all households +1.01 points, beyond its record 1.00"]),
        (3.21, []),  # move -0.49
        (3.19, ["B/Q1 2026-10: the gap moved -0.51 points in a month, beyond its record 0.50"]),
    ],
    ids=["within", "at the gap record", "beyond the gap record", "within the move record", "beyond the move record"],
)
def test_a_new_month_beyond_a_groups_record_is_named(october, expected):
    """PY-DEC-004: a new month beyond a group's record gap, or its record monthly move, is named; up to the record it isn't

    Given a published history in which the poorest fifth's gap to all households reached 1.00 point and moved by at most 0.50 in a month
    When a build adds October with all households at 3.0% and the poorest fifth at 3.9, 4.0, 4.01, 3.21 or 3.19%
    Then a gap or a move up to the record passes
    And one beyond it is named, with the group, the month, the value and the record
    """
    old = rows({("all", "all"): ALL, ("B", "Q1"): Q1})
    new = rows({("all", "all"): {**ALL, "2026-10": 3.0}, ("B", "Q1"): {**Q1, "2026-10": october}})
    assert rd.beyond_records(old, new) == expected


def test_a_group_with_no_history_is_named():
    """PY-DEC-005: a group that production never published is named, not compared with nothing

    Given a published history without the group renters
    When a build adds a month for renters
    Then the renters are named as a group with no published history
    And months already published are never judged again
    """
    old = rows({("all", "all"): ALL})
    new = rows({("all", "all"): {**ALL, "2026-10": 3.0}, ("tenure", "renter"): {"2026-10": 3.2}})
    assert rd.beyond_records(old, new) == ["tenure/renter: a group with no published history"]
    assert (
        rd.beyond_records(rows({("all", "all"): ALL, ("B", "Q1"): Q1}), rows({("all", "all"): ALL, ("B", "Q1"): Q1}))
        == []
    )


def test_the_inputs_record_lists_every_file_the_store_read(tmp_path):
    """PY-DEC-006: the inputs record lists every archived file the store has read, per dataset

    Given a store whose load record has two snapshots of one dataset and one of another, one read twice
    When the inputs record is made
    Then it lists each dataset once with its files' SHA-256 sorted and without repeats
    And a store with no load record gives an empty record
    And the difference with an older record names the new file and the new dataset
    """
    lines = [
        {"archive_dataset": "elstat/doc-585819", "sha256": SHA["c"]},
        {"archive_dataset": "elstat/doc-585819", "sha256": SHA["a"]},
        {"archive_dataset": "eurostat/prc_hicp_minr", "sha256": SHA["e"]},
        {"archive_dataset": "eurostat/prc_hicp_minr", "sha256": SHA["e"]},
    ]
    (tmp_path / "loaded.jsonl").write_text("".join(json.dumps(x) + "\n" for x in lines), encoding="utf-8")
    got = rd.store_inputs(tmp_path)
    assert got == {"elstat/doc-585819": [SHA["a"], SHA["c"]], "eurostat/prc_hicp_minr": [SHA["e"]]}
    assert rd.store_inputs(tmp_path / "none") == {}
    diff = rd.input_changes({"elstat/doc-585819": [SHA["a"]]}, got)
    assert diff["new_files"] == [f"elstat/doc-585819 {SHA['c'][:12]}", f"eurostat/prc_hicp_minr {SHA['e'][:12]}"]
    assert diff["new_datasets"] == ["eurostat/prc_hicp_minr"] and diff["gone_files"] == diff["gone_datasets"] == []


def test_a_figure_in_the_text_holds_the_build_when_its_dataset_changes():
    """PY-DEC-007: a build holds when a dataset a typed figure rests on changed, and only then

    Given a past figure in the text resting on ELSTAT's 2025 table 07, which the data can't recompute
    When a data-only build brings a new copy of that table, or only the month's new CPI file
    Then the first holds, naming the text's entry and the dataset
    And the second is promoted
    """
    quoted = {"glossary/imputed-rent.md#intro": ["elstat/doc-554284"]}
    live = {**PUBLISHED, "elstat/doc-554284": [SHA["d"]]}
    revised = with_file(with_file(live, "elstat/doc-585819", SHA["c"]), "elstat/doc-554284", SHA["e"])
    held = decide(inputs=revised, production_inputs=live, quoted=quoted)
    assert held.verdict == rd.HOLD
    assert held.reasons == [
        "the text's figures in glossary/imputed-rent.md#intro rest on elstat/doc-554284, which changed: read them again"
    ]
    assert decide(quoted=quoted).verdict == rd.PROMOTE
