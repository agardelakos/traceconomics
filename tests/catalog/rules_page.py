"""The wiki page Rules-guides-and-sensors: every hard rule, what steers away from it, what sees a break.

    python -I tests/catalog/rules_page.py --out WIKI_DIR --repo OWNER/NAME

Writes `Rules-guides-and-sensors.md` into WIKI_DIR from the registry `tests/catalog/rules.toml`, checked
against the sources first (`problems()`): the registry holds exactly the hard rules of `AGENTS.md`,
word for word and in order; every rule names a guide; every test it names exists; every file it
names exists; every rule a machine checks names a sensor test (one that breaks the rule on purpose).
While anything disagrees, nothing is written. Never edited by hand.

The same repository gives the same bytes. Standard library only.
"""

from __future__ import annotations

import argparse
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = Path("tests/catalog/rules.toml")
AGENTS = Path("AGENTS.md")
STRENGTHS = ("strong", "partial", "review")
# Where each suite's cases are declared: a Python docstring's first line, a browser test's `id:`.
DECLARED = re.compile(r'(?:"""|id: ")((?:PY|VT|PW|SEL)-[A-Z0-9]+-\d{3})\b')
SUITE_PAGES = {"PY": "Tests-pytest", "VT": "Tests-Vitest", "PW": "Tests-Playwright", "SEL": "Tests-Selenium"}
# A path named in backticks: with a slash, or a file name with a known extension.
PATH = re.compile(r"`([\w./-]+(?:/[\w./-]*|\.(?:py|toml|mjs|ts|md|txt|json|yml)))`")
HEAD = "> Generated, do not edit. Made from the repository on every wiki run (`tests/catalog/rules_page.py`); a correction goes into the sensor or into `tests/catalog/rules.toml`, and this page follows.\n"
LABEL = {"strong": "strong", "partial": "partial", "review": "review only"}


def hard_rules(text: str) -> list[str]:
    """The bullets of AGENTS.md's "Hard rules" section, in order."""
    m = re.search(r"^## Hard rules\b.*?$(.*?)^## ", text, re.M | re.S)
    if not m:
        raise SystemExit(f"no `## Hard rules` section in {AGENTS}")
    return [line[2:].strip() for line in m.group(1).splitlines() if line.startswith("- ")]


def registry(root: Path = ROOT) -> list[dict]:
    """The registry's rules, in order."""
    return tomllib.loads((root / REGISTRY).read_text(encoding="utf-8"))["rule"]


def declared_ids(root: Path = ROOT) -> set[str]:
    """Every test case ID declared in the test code, of all suites."""
    files = [
        *(root / "tests").rglob("*.py"),
        *(root / "site/tests").rglob("*.ts"),
        *(root / "site/src").rglob("*.test.ts"),
    ]
    return {m for f in files if "fixtures" not in f.parts for m in DECLARED.findall(f.read_text(encoding="utf-8"))}


def problems(root: Path = ROOT, rules: list[dict] | None = None) -> list[str]:
    """Where the registry and the sources disagree, one line each."""
    rules = registry(root) if rules is None else rules
    out = []
    bullets = hard_rules((root / AGENTS).read_text(encoding="utf-8"))
    listed = [r.get("rule", "") for r in rules]
    out += [f"AGENTS.md hard rule without an entry in {REGISTRY}: {b}" for b in bullets if b not in listed]
    out += [f"{REGISTRY} entry for no hard rule in AGENTS.md: {r}" for r in listed if r not in bullets]
    if not out and listed != bullets:
        out.append(f"{REGISTRY} lists the hard rules in another order than AGENTS.md")
    ids = declared_ids(root)
    for r in rules:
        name = r.get("rule", "?")[:50]
        strength = r.get("strength")
        if strength not in STRENGTHS:
            out.append(f"{name}: strength {strength!r}, not one of {', '.join(STRENGTHS)}")
            continue
        if not r.get("guides"):
            out.append(f"{name}: no guides listed")
        if not r.get("sensors"):
            out.append(f"{name}: no sensors listed")
        out += [f"{name}: names {t}, which no test declares" for t in r.get("sensor_tests", []) if t not in ids]
        if strength != "review" and not r.get("sensor_tests"):
            out.append(f"{name}: checked by a machine but no sensor test proves the sensor fires")
        if strength == "partial" and not r.get("gap", "").strip():
            out.append(f"{name}: partial, but no `gap` says what the sensors can't see")
        if strength == "review" and not r.get("why", "").strip():
            out.append(f"{name}: review only, but no `why`")
        for text in r.get("guides", []) + r.get("sensors", []):
            out += [f"{name}: names `{p}`, which doesn't exist" for p in PATH.findall(text) if not (root / p).exists()]
    return out


def page(rules: list[dict], repo: str) -> str:
    """The page's Markdown."""

    def esc(text: str) -> str:
        return str(text).replace("|", "\\|").replace("\n", " ")

    def link(case: str) -> str:
        return f"[{case}]({SUITE_PAGES[case.split('-')[0]]}#{case.lower()})"

    def src(text: str) -> str:
        return PATH.sub(lambda m: f"[`{m[1]}`](https://github.com/{repo}/blob/main/{m[1]})", esc(text))

    counts = {s: sum(r["strength"] == s for r in rules) for s in STRENGTHS}
    lines = [
        HEAD,
        "# Rules: guides and sensors",
        "",
        f"[`AGENTS.md`](https://github.com/{repo}/blob/main/AGENTS.md) lists {len(rules)} hard rules that "
        "bind every contributor, person or coding agent. A rule written down but not enforced holds only "
        "while every reader obeys it, so each one is listed here in the terms of "
        "[Harness engineering](Harness-engineering): its **guides**, which steer a contributor or an agent "
        "away from a break before it is made, and its **sensors**, which see a break once it is made, with "
        "how strongly they hold, the gaps included. Every rule's first guide is its own line in `AGENTS.md`; "
        "the table lists the others. All the sensors are computational: they give the same answer every "
        "time. None is inferential (a model judging): where no machine can see a break, a person decides.",
        "",
        f"**{counts['strong']} strong** (a machine refuses every break it can see), **{counts['partial']} "
        f"partial** (a machine refuses some breaks; the gap is named), **{counts['review']} review only** "
        "(only a person can judge them; the reason is given).",
        "",
        "A sensor that has quietly stopped working looks exactly like a clean repository. So every sensor "
        "is proved by a **sensor test**: it breaks the rule on purpose, in a temporary copy, and expects "
        "the sensor to refuse it with a message naming the rule. [Checks](Checks) lists every check that runs, "
        "by when it runs.",
        "",
        "| Rule | Strength | Guides | Sensors | Sensor tests |",
        "| --- | --- | --- | --- | --- |",
    ]
    for r in rules:
        sensors = "<br>".join(src(g) for g in r["sensors"])
        note = r.get("gap") or r.get("why")
        if note:
            sensors += f"<br>*{'Gap' if r.get('gap') else 'Why'}:* {esc(note)}"
        proved = ", ".join(link(t) for t in r.get("sensor_tests", [])) or "–"
        guides = "<br>".join(src(g) for g in r["guides"])
        lines.append(f"| {src(r['rule'])} | {LABEL[r['strength']]} | {guides} | {sensors} | {proved} |")
    lines += [
        "",
        "## Keeping this page true",
        "",
        f"The page is made from [`{REGISTRY.as_posix()}`](https://github.com/{repo}/blob/main/{REGISTRY.as_posix()}). "
        "A test fails when `AGENTS.md` gains, loses or rewords a hard rule without its entry, when an "
        "entry has no guide, when it names a test or a file that doesn't exist, and when a rule that a "
        "machine checks has no sensor test.",
    ]
    return "\n".join(lines)


def generate(out: Path, repo: str, root: Path | None = None) -> list[str]:
    """Write the page into `out`; refuse (SystemExit) while the registry and the sources disagree."""
    root = ROOT if root is None else root
    rules = registry(root)
    found = problems(root, rules)
    if found:
        raise SystemExit("Rules page not written:\n  " + "\n  ".join(found))
    out.mkdir(parents=True, exist_ok=True)
    (out / "Rules-guides-and-sensors.md").write_text(page(rules, repo).rstrip() + "\n", encoding="utf-8", newline="\n")
    return ["Rules-guides-and-sensors"]


def main(argv=None):
    """The command line."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--repo", required=True)
    a = ap.parse_args(argv)
    print("wrote " + ", ".join(generate(a.out, a.repo)))


if __name__ == "__main__":
    sys.exit(main())
