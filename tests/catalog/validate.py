"""The catalog's quality gate: every case well formed, every ID unique, the mapping consistent.

    python -I tests/catalog/validate.py catalog.json [--strict tests/catalog/strict.toml]
        [--mapping tests/catalog/cases.toml] [--obsolete obsolete.json] [--require-all]

Rules (the code in brackets is what a finding is listed under):

- [missing-id]     a test without a case ID;
- [bad-id]         an ID not of the form PREFIX-AREA-NNN, or with another suite's prefix;
- [duplicate-id]   one ID on tests in different files or suites (one file may share an ID across
                   the examples of one outline);
- [missing-steps]  a case without Given, When or Then;
- [text]           steps out of order, a line that isn't a step, examples with different steps;
- [reused-id]      an ID that once belonged to a test now removed: IDs are never reused;
- [mapping]        cases.toml names an unknown ID, the wrong suite, or an ID twice;
- [unmapped]       a Playwright or Selenium case that cases.toml doesn't list;
- [incomplete]     a suite missing from the catalog (with --require-all).

A ratchet: findings in the files `strict.toml` lists (or everywhere, once it says `all = true`)
fail the check; elsewhere they are warnings, so the backfill can go file by file without
switching the gate off. `[unmapped]` fails once `mapping_complete = true`. `[bad-id]`,
`[duplicate-id]`, `[reused-id]` and `[mapping]` always fail: they break traceability wherever
they are.

Standard library only.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import sys
import tomllib
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from cases import ID, SUITES, Case, missing_steps  # noqa: E402

ALWAYS = {"bad-id", "duplicate-id", "reused-id", "mapping", "incomplete"}
TC = re.compile(r"^TC-[A-Z][A-Z0-9]{1,9}-\d{3}$")


@dataclass
class Finding:
    rule: str
    where: str          # file:line or the mapping file
    message: str
    error: bool = False

    def __str__(self):
        return f"{'ERROR' if self.error else 'warn '} [{self.rule}] {self.where}: {self.message}"


def load_toml(path: Path | None) -> dict:
    if path is None or not path.is_file():
        return {}
    with path.open("rb") as f:
        return tomllib.load(f)


def strict_for(strict: dict):
    every = bool(strict.get("all"))
    patterns = list(strict.get("files", []))
    return lambda file: every or any(fnmatch.fnmatch(file, p) for p in patterns)


def check(catalog: dict, strict: dict, mapping: dict, obsolete: set[str], require_all: bool) -> list[Finding]:
    is_strict = strict_for(strict)
    cases = [Case.from_json(c) for c in catalog["cases"]]
    out: list[Finding] = []

    def add(rule, case_or_where, message, strict_file=None):
        if isinstance(case_or_where, Case):
            where, file = f"{case_or_where.file}:{case_or_where.line}", case_or_where.file
        else:
            where, file = case_or_where, strict_file
        error = rule in ALWAYS or (file is not None and is_strict(file))
        out.append(Finding(rule, where, message, error))

    if require_all:
        for s in catalog.get("missing", []):
            add("incomplete", "catalog", f"the {s} suite was not collected")

    seen: dict[str, list[Case]] = defaultdict(list)
    for c in cases:
        label = c.title or c.node
        if c.id is None:
            add("missing-id", c, f"no case ID: {label}")
        else:
            m = ID.match(c.id)
            if not m:
                add("bad-id", c, f"{c.id} is not PREFIX-AREA-NNN")
            elif m.group(1) != SUITES[c.suite]:
                add("bad-id", c, f"{c.id} in the {c.suite} suite should start with {SUITES[c.suite]}-")
            seen[c.id].append(c)
            if c.id in obsolete:
                add("reused-id", c, f"{c.id} belonged to a test that was removed; take a new number")
        if c.id is not None:
            gaps = missing_steps(c)
            if gaps:
                add("missing-steps", c, f"{c.id}: no {', '.join(gaps)}")
        for p in c.problems:
            if p == "no docstring" or p.startswith("first line is not"):
                continue            # already a missing-id
            add("text", c, f"{c.id or label}: {p}")
    for cid, where in seen.items():
        if len(where) > 1:
            places = ", ".join(f"{c.file}:{c.line}" for c in where)
            add("duplicate-id", where[0], f"{cid} is on more than one test: {places}")

    # The cross-suite mapping.
    known = {c.id: c for c in cases if c.id}
    mapped: dict[str, str] = {}
    for tc, entry in sorted(mapping.items()):
        if not TC.match(tc):
            add("mapping", "cases.toml", f"{tc} is not TC-AREA-NNN")
        if not isinstance(entry, dict) or not entry.get("title"):
            add("mapping", "cases.toml", f"{tc} has no title")
            continue
        for suite in ("playwright", "selenium"):
            for cid in entry.get(suite, []):
                if cid in mapped:
                    add("mapping", "cases.toml", f"{cid} is mapped twice ({mapped[cid]} and {tc})")
                mapped[cid] = tc
                c = known.get(cid)
                if c is None:
                    add("mapping", "cases.toml", f"{tc} names {cid}, which no test carries")
                elif c.suite != suite:
                    add("mapping", "cases.toml", f"{tc} lists {cid} under {suite}, but it is a {c.suite} case")
        if not entry.get("playwright") and not entry.get("selenium"):
            add("mapping", "cases.toml", f"{tc} names no case")
        elif not (entry.get("playwright") and entry.get("selenium")) and not entry.get("why"):
            add("mapping", "cases.toml", f"{tc} is in one suite only: say why (`why = \"…\"`)")
    complete = bool(strict.get("mapping_complete"))
    for c in cases:
        if c.suite in ("playwright", "selenium") and c.id and c.id not in mapped:
            out.append(Finding("unmapped", f"{c.file}:{c.line}", f"{c.id} is not in cases.toml", complete))
    return out


def summary(findings: list[Finding], catalog: dict) -> str:
    errors = sum(f.error for f in findings)
    per = defaultdict(int)
    for f in findings:
        per[f.rule] += 1
    total = len(catalog["cases"])
    with_id = sum(1 for c in catalog["cases"] if c["id"])
    line = f"{total} cases, {with_id} with an ID; {errors} errors, {len(findings) - errors} warnings"
    if per:
        line += " (" + ", ".join(f"{k} {v}" for k, v in sorted(per.items())) + ")"
    return line


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("catalog", type=Path)
    ap.add_argument("--strict", type=Path, default=HERE / "strict.toml")
    ap.add_argument("--mapping", type=Path, default=HERE / "cases.toml")
    ap.add_argument("--obsolete", type=Path, help="JSON object whose keys are the obsolete IDs")
    ap.add_argument("--require-all", action="store_true", help="fail if a suite wasn't collected")
    ap.add_argument("--quiet", action="store_true", help="list errors only")
    a = ap.parse_args(argv)
    catalog = json.loads(a.catalog.read_text(encoding="utf-8"))
    obsolete = set(json.loads(a.obsolete.read_text(encoding="utf-8"))) if a.obsolete and a.obsolete.is_file() else set()
    findings = check(catalog, load_toml(a.strict), load_toml(a.mapping), obsolete, a.require_all)
    for f in sorted(findings, key=lambda f: (not f.error, f.where)):
        if f.error or not a.quiet:
            print(f)
    print(summary(findings, catalog))
    return 1 if any(f.error for f in findings) else 0


if __name__ == "__main__":
    sys.exit(main())
