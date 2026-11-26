"""The wiki page Rules-and-their-guards can't fall behind the rules: the registry
`tests/catalog/rules.toml` holds exactly AGENTS.md's hard rules, every test and file it names exists,
and every rule a machine guards has a guard test (tests/catalog/rules_page.py)."""

import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / "catalog"))
import rules_page  # noqa: E402 - found through the path set just above
from guards import private_text  # noqa: E402

pytestmark = pytest.mark.repository

ROOT = Path(__file__).resolve().parent.parent


def made_up(tmp_path: Path) -> Path:
    """A copy of what the registry is checked against: AGENTS.md, the registry, the tests and files it names."""
    for name in ["AGENTS.md", "tests/catalog/rules.toml"]:
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / name, tmp_path / name)
    for rule in rules_page.registry(ROOT):
        for text in rule["guards"]:
            for p in rules_page.PATH.findall(text):
                (tmp_path / p).parent.mkdir(parents=True, exist_ok=True)
                if (ROOT / p).is_dir():
                    (tmp_path / p).mkdir(exist_ok=True)
                elif not (tmp_path / p).exists():
                    (tmp_path / p).write_text("", encoding="utf-8")
    ids = "\n".join(f'"""{i}: x' for rule in rules_page.registry(ROOT) for i in rule.get("guard_tests", []))
    (tmp_path / "tests/test_ids.py").write_text(ids + "\n", encoding="utf-8")
    return tmp_path


def test_the_real_registry_matches_the_rules():
    """PY-RULES-001: The real registry holds every hard rule, and everything it names exists

    Given AGENTS.md, tests/catalog/rules.toml and the test code
    When the page generator compares them
    Then it finds no rule without an entry, no entry without a rule, nothing out of order
    And every guard test and file the registry names exists, and every guarded rule has a guard test
    """
    assert rules_page.problems(ROOT) == []


def test_a_new_or_reworded_rule_without_its_entry_is_found(tmp_path):
    """PY-RULES-002: A hard rule added, reworded or moved in AGENTS.md without the registry is reported

    Given a made-up repository whose registry matches its AGENTS.md
    When AGENTS.md gains a rule, then has a rule reworded, then has two rules swapped
    Then each change is reported until the registry follows
    """
    root = made_up(tmp_path)
    assert rules_page.problems(root) == []
    agents = (root / "AGENTS.md").read_text(encoding="utf-8")
    first, second = rules_page.hard_rules(agents)[:2]

    (root / "AGENTS.md").write_text(agents.replace(f"- {first}\n", f"- {first}\n- Never planted.\n"), encoding="utf-8")
    assert rules_page.problems(root) == [
        "AGENTS.md hard rule without an entry in tests/catalog/rules.toml: Never planted."
    ]

    (root / "AGENTS.md").write_text(agents.replace(first, first + " Reworded."), encoding="utf-8")
    found = rules_page.problems(root)
    assert found[0].startswith("AGENTS.md hard rule without an entry") and found[1].startswith(
        "tests/catalog/rules.toml entry for no hard rule"
    )

    swapped = agents.replace(f"- {first}\n- {second}\n", f"- {second}\n- {first}\n")
    (root / "AGENTS.md").write_text(swapped, encoding="utf-8")
    assert rules_page.problems(root) == [
        "tests/catalog/rules.toml lists the hard rules in another order than AGENTS.md"
    ]


def test_an_entry_that_promises_too_much_is_found(tmp_path):
    """PY-RULES-003: An entry naming a missing test or file, or claiming a guard it can't prove, is reported

    Given a made-up repository whose registry matches its AGENTS.md
    When entries name a missing test and file, or lose their guard tests, gap or reason, or get an unknown strength
    Then each is reported, naming the rule
    """
    root = made_up(tmp_path)
    rules = rules_page.registry(root)
    strong = [r for r in rules if r["strength"] == "strong"]
    partial = next(r for r in rules if r["strength"] == "partial")
    review = next(r for r in rules if r["strength"] == "review")
    strong[0]["guard_tests"] = ["PY-NOBODY-001"]
    strong[0]["guards"] = ["Checked by `tests/test_gone.py`"]
    strong[1]["guard_tests"] = []
    partial["gap"] = ""
    review["why"] = ""
    strong[2]["strength"] = "total"
    found = rules_page.problems(root, rules)
    assert len(found) == 6
    assert any("PY-NOBODY-001, which no test declares" in p for p in found)
    assert any("`tests/test_gone.py`, which doesn't exist" in p for p in found)
    assert any("no guard test proves the guard fires" in p for p in found)
    assert any("partial, but no `gap`" in p for p in found)
    assert any("review only, but no `why`" in p for p in found)
    assert any("strength 'total'" in p for p in found)


def test_the_page_is_not_written_while_anything_disagrees(tmp_path):
    """PY-RULES-004: Nothing is written while the registry disagrees with the sources

    Given a made-up repository whose AGENTS.md has a rule the registry lacks
    When the page is generated
    Then it stops with the disagreement and writes no page
    """
    root = made_up(tmp_path / "repo")
    agents = root / "AGENTS.md"
    agents.write_text(
        agents.read_text(encoding="utf-8").replace(
            "## Hard rules (one line each)\n\n", "## Hard rules (one line each)\n\n- Never planted.\n"
        ),
        encoding="utf-8",
    )
    with pytest.raises(SystemExit, match="Never planted"):
        rules_page.generate(tmp_path / "wiki", "o/r", root)
    assert not (tmp_path / "wiki").exists()


def test_the_real_page_gives_the_same_bytes_and_nothing_private(tmp_path):
    """PY-RULES-005: The real page is byte-identical from run to run, lists every rule, and holds nothing private

    Given the repository as it is
    When the page is generated twice through the command line
    Then both files are byte-identical, with one table row per hard rule and its guard tests linked
    And the private-text guard finds nothing in it
    """
    for out in ("a", "b"):
        rules_page.main(["--out", str(tmp_path / out), "--repo", "o/r"])
    a = (tmp_path / "a/Rules-and-their-guards.md").read_bytes()
    assert a == (tmp_path / "b/Rules-and-their-guards.md").read_bytes()
    text = a.decode("utf-8")
    rules = rules_page.registry(ROOT)
    assert sum(line.startswith("| ") for line in text.splitlines()) == len(rules) + 2  # the header and its separator
    assert (
        "[PY-GUARD-001](Tests-pytest#py-guard-001)" in text
        and "[PW-GUARD-003](Tests-playwright#pw-guard-003)" not in text
    )
    assert "[PW-GUARD-003](Tests-Playwright#pw-guard-003)" in text
    assert private_text(tmp_path, ["a/Rules-and-their-guards.md"], []) == []
