"""The wiki's test pages, generated from the stored catalog and run history. Never edited by hand.

    python -I tests/catalog/wiki.py --store DIR --out WIKI_DIR --repo OWNER/NAME [--last 10] [--window 20]

DIR is the branch `test-history` (see history.py); WIKI_DIR a checkout of the wiki. Writes:

    Tests.md                 the overview: the newest run of each kind, cases per suite, results without a case
    Tests-<Suite>.md         every case of one suite by area: its steps, examples, defects, source link,
                             its last results and its flakiness
    Tests-Runs.md            the recent runs of each kind
    Tests-Obsolete.md        cases whose test was removed, with the last commit that had them
    _Sidebar.md              only the block between `<!-- generated:start -->` and `<!-- generated:end -->`

and removes any other `Tests-*.md` it wrote before. Every page starts with "Generated, do not edit".

Flakiness: over a case's last WINDOW results on pushes to main that weren't skipped, the share of
consecutive pairs whose result changed (a pass followed by a fail, or the reverse); a pass that
needed a retry counts as one change (the way back to a clean pass doesn't count again). Shown once a case has at least 5 such results; below
that it says so. A rate, not a verdict: a real regression and its fix show up as two changes.

Standard library only.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

SUITE_PAGE = {
    "pytest": "Tests-pytest",
    "selenium": "Tests-Selenium",
    "playwright": "Tests-Playwright",
    "vitest": "Tests-Vitest",
}
SUITE_NAME = {"pytest": "pytest", "selenium": "Selenium", "playwright": "Playwright", "vitest": "Vitest"}
TRIGGER_NAME = {
    "push": "Push to main (CI, made-up data)",
    "ui-test": "Release: full browser suite, before upload",
    "smoke": "Release: smoke set on the preview",
    "promote": "Release: check after a promote",
}
MARK = {"passed": "✓", "failed": "✗", "flaky": "≈", "skipped": "–", None: "·"}
HEAD = "> Generated, do not edit. Made from the test catalog and the run history on every run; a correction goes into the test, and this page follows.\n"
START, END = "<!-- generated:start -->", "<!-- generated:end -->"
MIN_FOR_RATE = 5


def load(store: Path):
    catalog = (
        json.loads((store / "catalog.json").read_text(encoding="utf-8"))
        if (store / "catalog.json").is_file()
        else {"cases": [], "commit": None}
    )
    obsolete = (
        json.loads((store / "obsolete.json").read_text(encoding="utf-8")) if (store / "obsolete.json").is_file() else {}
    )
    runs: dict[str, list[dict]] = {}
    for folder in sorted((store / "runs").glob("*")) if (store / "runs").is_dir() else []:
        runs[folder.name] = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(folder.glob("*.json"))]
    return catalog, obsolete, runs


def esc(text: str) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def anchor(case_id: str) -> str:
    return case_id.lower()


def flakiness(results: list[str]) -> float | None:
    seq = [r for r in results if r != "skipped"]
    if len(seq) < MIN_FOR_RATE:
        return None
    changes = sum(1 for a, b in zip(seq, seq[1:]) if a != b and not (a == "flaky" and b == "passed"))
    return changes / (len(seq) - 1)


def history(runs: dict[str, list[dict]], trigger: str, case_id: str, n: int) -> list[str | None]:
    return [r["cases"].get(case_id, {}).get("result") for r in runs.get(trigger, [])[-n:]]


def short(commit: str | None) -> str:
    return (commit or "")[:7]


def commit_link(repo: str, commit: str | None) -> str:
    return f"[`{short(commit)}`](https://github.com/{repo}/commit/{commit})" if commit else "–"


def run_line(repo: str, r: dict) -> str:
    totals = defaultdict(int)
    for s in r["suites"].values():
        for k in ("passed", "failed", "flaky", "skipped"):
            totals[k] += s.get(k, 0)
    env = r.get("environment", {})
    where = ", ".join(
        v for v in (env.get("platform"), env.get("browser"), env.get("data") and f"{env['data']} data") if v
    )
    build = f"build `{r['build']}`" if r.get("build") else ""
    report = f"[report]({r['report']})" if r.get("report") else ""
    status = "✗ failed" if totals["failed"] else "✓ passed"
    return (
        f"| {r['started'][:16].replace('T', ' ')} | {status} | {commit_link(repo, r.get('commit'))} {build} "
        f"| {totals['passed']} | {totals['failed']} | {totals['flaky']} | {totals['skipped']} | {esc(where)} | {report} |"
    )


RUNS_HEAD = "| Started (UTC) | Result | Commit | Passed | Failed | Flaky | Skipped | Environment | |\n|---|---|---|---|---|---|---|---|---|"


def page_overview(repo, catalog, obsolete, runs) -> str:
    out = ["# Test cases and runs\n", HEAD]
    out.append(
        "Every automated test carries its case (an ID and Given/When/Then). How it works: "
        "[Test management as code](Test-management-as-code).\n"
    )
    out.append("## Newest run of each kind\n")
    out.append(RUNS_HEAD)
    for t in TRIGGER_NAME:
        if runs.get(t):
            out.append(run_line(repo, runs[t][-1]).replace("| ", f"| {TRIGGER_NAME[t]}: ", 1))
    if not any(runs.values()):
        out.append("| No run recorded yet | | | | | | | | |")
    out.append("\n## Cases per suite\n")
    out.append(
        "| Suite | Cases | Results without a case yet (newest push; an outline counts each example) |\n|---|---|---|"
    )
    newest = runs.get("push", [])[-1:] or [{}]
    per = defaultdict(int)
    for c in catalog["cases"]:
        if c["id"]:
            per[c["suite"]] += 1
    for suite, pg in SUITE_PAGE.items():
        missing = newest[0].get("no_case", {}).get(suite, "–")
        out.append(f"| [{SUITE_NAME[suite]}]({pg}) | {per.get(suite, 0)} | {missing} |")
    out.append(
        f"\nObsolete cases: {len(obsolete)} ([list](Tests-Obsolete)). Recent runs: [Tests-Runs](Tests-Runs). "
        f"Catalog as of commit {commit_link(repo, catalog.get('commit'))}.\n"
    )
    out.append("Legend: ✓ passed, ✗ failed, ≈ passed on a retry, – skipped, · not in that run.\n")
    return "\n".join(out)


def page_suite(repo, suite, catalog, runs, last, window) -> str:
    cases = [c for c in catalog["cases"] if c["suite"] == suite and c["id"]]
    out = [f"# {SUITE_NAME[suite]} cases\n", HEAD]
    if not cases:
        out.append("No cases yet.\n")
        return "\n".join(out)
    by_area = defaultdict(list)
    for c in cases:
        by_area[c["id"].split("-")[1]].append(c)
    out.append("| ID | Title | Last runs on main | Flakiness | Defects |\n|---|---|---|---|---|")
    for ar in sorted(by_area):
        for c in sorted(by_area[ar], key=lambda c: c["id"]):
            marks = "".join(MARK[r] for r in history(runs, "push", c["id"], last)) or "·"
            rate = flakiness([r for r in history(runs, "push", c["id"], window) if r])
            rate_s = "too few runs" if rate is None else f"{rate:.0%}"
            defects = " ".join(f"#{d}" for d in c.get("defects", [])) or ""
            out.append(f"| [{c['id']}](#{anchor(c['id'])}) | {esc(c['title'])} | {marks} | {rate_s} | {defects} |")
    commit = catalog.get("commit") or "main"
    for ar in sorted(by_area):
        out.append(f"\n## {ar}\n")
        for c in sorted(by_area[ar], key=lambda c: c["id"]):
            out.append(f"### {c['id']}\n")
            out.append(
                f"**{esc(c['title'])}** · [`{c['file']}`](https://github.com/{repo}/blob/{commit}/{c['file']}#L{c['line']})"
                + (f" · tags: {', '.join(c['tags'])}" if c.get("tags") else "")
                + "\n"
            )
            for word, key in (("Given", "given"), ("When", "when"), ("Then", "then")):
                for i, step in enumerate(c.get(key, [])):
                    out.append(f"- **{word if i == 0 else 'And'}** {esc(step)}")
            if c.get("examples"):
                out.append("\nExamples: " + ", ".join(f"`{esc(e)}`" for e in c["examples"]))
            if c.get("defects"):
                out.append(
                    "\nDefects: " + ", ".join(f"[#{d}](https://github.com/{repo}/issues/{d})" for d in c["defects"])
                )
            rel = [(t, history(runs, t, c["id"], last)) for t in ("ui-test", "smoke", "promote")]
            rel = [(t, h) for t, h in rel if any(h)]
            if rel:
                out.append("\nRelease runs: " + "; ".join(f"{t} {''.join(MARK[r] for r in h)}" for t, h in rel))
            out.append("")
    return "\n".join(out)


def page_runs(repo, runs, n=30) -> str:
    out = ["# Test runs\n", HEAD]
    for t, name in TRIGGER_NAME.items():
        out.append(f"## {name}\n")
        rs = runs.get(t, [])
        if not rs:
            out.append("None recorded yet.\n")
            continue
        out.append(RUNS_HEAD)
        out += [run_line(repo, r) for r in reversed(rs[-n:])]
        out.append("")
    return "\n".join(out)


def page_obsolete(repo, obsolete) -> str:
    out = [
        "# Obsolete cases\n",
        HEAD,
        "A case whose test was removed. Its ID is never used again, so a past run is always read against the case it ran.\n",
    ]
    if not obsolete:
        out.append("None yet.\n")
        return "\n".join(out)
    out.append("| ID | Suite | Title | Last commit with it | Removed in |\n|---|---|---|---|---|")
    for cid, o in sorted(obsolete.items()):
        out.append(
            f"| {cid} | {SUITE_NAME.get(o['suite'], o['suite'])} | {esc(o['title'])} | "
            f"{commit_link(repo, o.get('last_commit'))} | {commit_link(repo, o.get('removed_in'))} |"
        )
    return "\n".join(out) + "\n"


def sidebar(text: str) -> str:
    # One more item of the hand-written "Testing" list, with the generated pages nested under it: the
    # block sits right after that list's last item (wiki/_Sidebar.md). Both markers are indented, so
    # the Markdown keeps them inside the list instead of ending it there and starting a second one.
    block = "\n".join(
        [
            START,
            "- [Test cases and runs](Tests)",
            *[f"  - [{SUITE_NAME[s]}]({p})" for s, p in SUITE_PAGE.items()],
            "  - [Runs](Tests-Runs)",
            "  - [Obsolete](Tests-Obsolete)",
            "  " + END,
        ]
    )
    if START in text and END in text:
        return re.sub(re.escape(START) + r".*?" + re.escape(END), lambda _: block, text, flags=re.S)
    return (text.rstrip() + "\n\n" if text.strip() else "") + block + "\n"


def generate(store: Path, out: Path, repo: str, last: int, window: int) -> list[str]:
    catalog, obsolete, runs = load(store)
    pages = {
        "Tests": page_overview(repo, catalog, obsolete, runs),
        "Tests-Runs": page_runs(repo, runs),
        "Tests-Obsolete": page_obsolete(repo, obsolete),
    }
    for suite, name in SUITE_PAGE.items():
        pages[name] = page_suite(repo, suite, catalog, runs, last, window)
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("Tests-*.md"):
        if old.stem not in pages:
            old.unlink()
    for name, text in pages.items():
        (out / f"{name}.md").write_text(text.rstrip() + "\n", encoding="utf-8", newline="\n")
    sb = out / "_Sidebar.md"
    sb.write_text(sidebar(sb.read_text(encoding="utf-8") if sb.is_file() else ""), encoding="utf-8", newline="\n")
    return sorted(pages)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--store", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--last", type=int, default=10, help="results shown per case")
    ap.add_argument("--window", type=int, default=20, help="results the flakiness rate looks at")
    a = ap.parse_args(argv)
    print("wrote " + ", ".join(generate(a.store, a.out, a.repo, a.last, a.window)))


if __name__ == "__main__":
    main()
