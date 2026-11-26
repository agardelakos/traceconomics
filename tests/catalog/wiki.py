"""The wiki's test pages, generated from the stored catalog and run history. Never edited by hand.

    python -I tests/catalog/wiki.py --store DIR --out WIKI_DIR --repo OWNER/NAME [--last 10] [--window 20]

DIR is the branch `test-history` (see history.py); WIKI_DIR a checkout of the wiki. Writes:

    Tests.md                 the overview: the newest run of each kind, cases per suite, results without a case
    Tests-<Suite>.md         every case of one suite by area: its steps, examples, defects, source link,
                             its last results and its flakiness
    Tests-Runs.md            the recent runs of each kind
    Tests-Obsolete.md        cases whose test was removed, with the last commit that had them
    Tests-Mutation.md        mutation testing of the engine, once a run is stored: the newest run's
                             score, the score over time (tests-mutation-score-*.svg), the result per
                             function, and every survivor with its change and, if written, its reason
    _Sidebar.md              only two blocks: the core's pages between `<!-- generated:start -->` and
                             `<!-- generated:end -->`, the testing showcase's (Selenium, the runs,
                             mutation testing) between `<!-- showcase:start -->` and `<!-- showcase:end -->`

and removes any other `Tests-*.md` it wrote before. Every page starts with "Generated, do not edit".

Selenium is the maintainer's testing showcase: nobody else has to keep it in step with the site. So
its page and the overview say whether it is: whether the newest recorded run on main has Selenium's
results and what they were, and how many Playwright cases the cross-suite mapping
(`tests/catalog/cases.toml`) doesn't list yet, each one a test Selenium may lack.

Flakiness: over a case's last WINDOW results on pushes to main that weren't skipped, the share of
consecutive pairs whose result changed (a pass followed by a fail, or the reverse); a pass that
needed a retry counts as one change (the way back to a clean pass doesn't count again). Shown once a case has at least 5 such results; below
that it says so. A rate, not a verdict: a real regression and its fix show up as two changes.

Standard library only.
"""

from __future__ import annotations

import argparse
import itertools
import json
import re
import sys
import tomllib
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # run with `python -I`: its folder isn't on the path
import code_charts as charts  # noqa: E402
from cases import renamed as renamed_ids  # noqa: E402
from code_map_pages import EQUIVALENT, engine_fingerprint, equivalent_reason  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]  # the repository, for the engine's source and the reasons

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
SHOWCASE_START, SHOWCASE_END = "<!-- showcase:start -->", "<!-- showcase:end -->"
MAPPING = Path("tests/catalog/cases.toml")  # the cross-suite mapping, relative to the repository
MIN_FOR_RATE = 5
LAYERS = ("unit", "integration", "repository")  # the pytest layers (tests/conftest.py)


def load(store: Path, renamed: dict[str, str] | None = None):
    """The stored catalog, the obsolete IDs and every run, a renamed case's results under its new ID."""
    renamed = renamed or {}
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
        runs[folder.name] = []
        for p in sorted(folder.glob("*.json")):
            r = json.loads(p.read_text(encoding="utf-8"))
            r["cases"] = {renamed.get(k, k): v for k, v in r.get("cases", {}).items()}
            runs[folder.name].append(r)
    return catalog, obsolete, runs


def load_mutation(store: Path) -> tuple[dict | None, list[dict]]:
    """The newest mutation testing result and every run's summary line, oldest first (tests/coverage/mutation.py)."""
    newest = store / "mutation.json"
    result = json.loads(newest.read_text(encoding="utf-8")) if newest.is_file() else None
    history_file = store / "mutation-history.jsonl"
    history = (
        [json.loads(line) for line in history_file.read_text(encoding="utf-8").splitlines() if line.strip()]
        if history_file.is_file()
        else []
    )
    if result is not None and not history:
        history = [result]  # a result stored before the history began
    return result, history


def esc(text: str) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def anchor(case_id: str) -> str:
    return case_id.lower()


def flakiness(results: list[str]) -> float | None:
    seq = [r for r in results if r != "skipped"]
    if len(seq) < MIN_FOR_RATE:
        return None
    changes = sum(1 for a, b in itertools.pairwise(seq) if a != b and not (a == "flaky" and b == "passed"))
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


def mutation_line(repo, result: dict) -> str:
    """The newest mutation result in a sentence: its score, the changes, the survivors, when and where."""
    survived = result["counts"].get("survived", 0)
    when = f"{result['started'][:10]}, " if result.get("started") else ""
    score = "–" if result.get("score") is None else f"{result['score']}%"
    return (
        f"**Mutation testing** of the engine: {score} of {result['mutants']} changes killed, "
        f"{survived} survived ({when}{commit_link(repo, result['commit'])})."
    )


def short_function(name: str) -> str:
    """`traceconomics.engine.chain.link` as `chain.link`."""
    return name.removeprefix("traceconomics.engine.")


def page_mutation(repo, result: dict, history: list[dict], root: Path) -> tuple[str, dict[str, str]]:
    """The mutation testing page, and its chart files: the newest run, the score over time, per function, survivors."""
    reasons_file = root / EQUIVALENT
    known = []
    if reasons_file.is_file():
        import tomllib

        known = tomllib.loads(reasons_file.read_text(encoding="utf-8")).get("equivalent", [])
    out = ["# Mutation testing\n"]
    out.append(
        "> Generated, do not edit. Made from the mutation testing runs on the branch test-history, on every "
        "update of the wiki.\n"
    )
    out.append(
        "Coverage says which lines a test runs; mutation testing says whether the tests would notice those "
        "lines going wrong. [mutmut](https://github.com/boxed/mutmut) changes the code of "
        "`src/traceconomics/engine` in small ways, one at a time (a `<` for a `<=`, a `break` for a "
        "`continue`), and runs the tests that run the engine on each. A change some test notices is "
        "*killed*; one no test notices *survived*: either the tests miss something, or the change behaves "
        "the same as the code. Started by hand (the `showcase` workflow), not on every push.\n"
    )
    counts = result["counts"]
    score = "–" if result.get("score") is None else f"{result['score']}%"
    when = f"on {result['started'][:10]} " if result.get("started") else ""
    run = f" ([the run]({result['run_url']}))" if result.get("run_url") else ""
    out.append("## Newest run\n")
    out.append(
        f"**Score: {score}** of {result['mutants']} changes killed (killed or timed out, of those tested), "
        f"{when}from commit {commit_link(repo, result['commit'])}{run}. Results: "
        + ", ".join(f"{k} {v}" for k, v in counts.items())
        + ".\n"
    )
    if result.get("source") != engine_fingerprint(root):
        out.append("> The engine's code has changed since this run: the result may no longer hold.\n")
    files: dict[str, str] = {}
    scored = [h for h in history if h.get("score") is not None]
    if scored:
        out.append("## Score over time\n")
        points = [((h.get("started") or "")[:10] or short(h["commit"]), h["score"]) for h in scored]
        files = charts.pair("tests-mutation-score", lambda th: charts.line(points, "Mutation score per run", th))
        out.append(charts.picture("tests-mutation-score", "Line chart: the mutation score of each run") + "\n")
        out.append("| Run | Commit | Changes | Killed | Survived | Score |\n|---|---|--:|--:|--:|--:|")
        for h in reversed(scored):
            c = h.get("counts", {})
            date = (h.get("started") or "")[:10] or "–"
            run_link = f"[{date}]({h['run_url']})" if h.get("run_url") else date
            out.append(
                f"| {run_link} | {commit_link(repo, h['commit'])} | {h['mutants']} | {c.get('killed', 0)} "
                f"| {c.get('survived', 0)} | {h['score']}% |"
            )
        out.append("")
    if result.get("functions"):
        out.append("## By function\n")
        out.append("| Function | Changes | Killed | Survived | Other |\n|---|--:|--:|--:|--:|")
        rows = sorted(result["functions"].items(), key=lambda kv: (-kv[1].get("survived", 0), kv[0]))
        for name, c in rows:
            killed = c.get("killed", 0) + c.get("timeout", 0) + c.get("caught by type check", 0)
            other = sum(c.values()) - killed - c.get("survived", 0)
            # The module's heading on Code-map-engine: `traceconomics.engine.chain` is #traceconomicsenginechain.
            anchor = "".join(name.split(".")[:3]).lower()
            out.append(
                f"| [`{short_function(name)}`](Code-map-engine#{anchor}) | {sum(c.values())} | {killed} "
                f"| {c.get('survived', 0)} | {other or ''} |"
            )
        out.append("")
    survivors = result.get("survivors", [])
    out.append("## Survivors\n")
    if not survivors:
        out.append("None: the tests noticed every change.\n")
        return "\n".join(out), files
    reasons = [equivalent_reason(sv, known) for sv in survivors]
    gaps = sum(r is None for r in reasons)
    out.append(
        f"{len(survivors)} survivor{'s' if len(survivors) != 1 else ''}: {gaps} not explained yet (a gap in the "
        "tests, or an equivalent change "
        f"not written down yet), {len(survivors) - gaps} that behave the same as the code, each with its "
        "reason (from `tests/coverage/mutation-equivalent.toml`).\n"
    )
    for sv, reason in zip(survivors, reasons, strict=True):
        out.append(f"### `{sv['function']}`: " + ("behaves the same" if reason else "not explained yet") + "\n")
        out += ["```diff", *sv["change"], "```", ""]
        if reason:
            out.append(f"Behaves the same: {esc(reason)}\n")
    return "\n".join(out), files


def load_mapping(root: Path) -> dict | None:
    """The cross-suite mapping (shared case -> its Playwright and Selenium IDs), or None without the file."""
    path = root / MAPPING
    return tomllib.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def selenium_status(repo, catalog, runs, mapping) -> str:
    """Whether the Selenium suite is in step with main: its newest result on main, and the Playwright cases unmapped."""
    pushes = runs.get("push", [])
    parts = []
    if not pushes:
        parts.append("No run on `main` recorded yet.")
    else:
        newest = pushes[-1]
        with_sel = [r for r in pushes if "selenium" in r.get("suites", {})]
        if not with_sel:
            parts.append("No run on `main` has Selenium's results yet.")
        else:
            last = with_sel[-1]
            failed = last["suites"]["selenium"].get("failed", 0)
            result = f"{failed} failed" if failed else "all passed"
            when = f"{last['started'][:10]}, commit {commit_link(repo, last.get('commit'))}"
            if last is newest:
                parts.append(f"Selenium ran on the newest recorded run on `main` ({when}): {result}.")
            else:
                parts.append(
                    f"**Behind `main`:** Selenium's newest results are from {when} ({result}); "
                    f"the newest recorded run on `main` ({newest['started'][:10]}, commit "
                    f"{commit_link(repo, newest.get('commit'))}) has none."
                )
    if mapping is not None:
        mapped = {cid for entry in mapping.values() for cid in entry.get("playwright", [])}
        unmapped = sorted(
            {c["id"] for c in catalog["cases"] if c["suite"] == "playwright" and c["id"] and c["id"] not in mapped}
        )
        if unmapped:
            parts.append(
                f"**{len(unmapped)} Playwright case{'s' if len(unmapped) != 1 else ''} not mapped yet** "
                "(`tests/catalog/cases.toml`), so Selenium may lack a matching test: "
                + ", ".join(f"[{cid}](Tests-Playwright#{anchor(cid)})" for cid in unmapped)
                + "."
            )
        else:
            parts.append("Every Playwright case is mapped to its Selenium case, or says why it has none.")
    return (
        "Selenium is part of the maintainer's [testing showcase](Testing-showcase): contributors never "
        "have to keep it in step, and the maintainer follows up. " + " ".join(parts) + "\n"
    )


def page_overview(repo, catalog, obsolete, runs, mutation=None, mapping=None) -> str:
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
    layers = defaultdict(int)
    for c in catalog["cases"]:
        if c["id"] and c.get("layer"):
            layers[c["layer"]] += 1
    if layers:
        out.append(
            "\npytest cases by layer: "
            + ", ".join(f"{k} {layers[k]}" for k in LAYERS if layers.get(k))
            + ". A unit test runs one of our components on its own, an integration test several of them "
            "through a real resource (an archive on disk, the store), a repository test checks the "
            "repository's own files and runs no package code ([Checks](Checks#repository-checks) lists them by file)."
        )
    out.append("\n" + selenium_status(repo, catalog, runs, mapping).rstrip())
    if mutation is not None:
        out.append("\n" + mutation_line(repo, mutation) + " [Mutation testing](Tests-Mutation).")
    out.append(
        f"\nObsolete cases: {len(obsolete)} ([list](Tests-Obsolete)). Recent runs: [Tests-Runs](Tests-Runs). "
        f"Catalog as of commit {commit_link(repo, catalog.get('commit'))}.\n"
    )
    out.append("Legend: ✓ passed, ✗ failed, ≈ passed on a retry, – skipped, · not in that run.\n")
    return "\n".join(out)


def page_suite(repo, suite, catalog, runs, last, window, mapping=None) -> str:
    cases = [c for c in catalog["cases"] if c["suite"] == suite and c["id"]]
    out = [f"# {SUITE_NAME[suite]} cases\n", HEAD]
    if suite == "selenium":
        out.append(selenium_status(repo, catalog, runs, mapping))
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
                + (f" · layer: {c['layer']}" if c.get("layer") else "")
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


def _replace(text: str, start: str, end: str, block: str) -> str:
    """The text with the block between `start` and `end` replaced, or the block added at the end."""
    if start in text and end in text:
        return re.sub(re.escape(start) + r".*?" + re.escape(end), lambda _: block, text, flags=re.S)
    return (text.rstrip() + "\n\n" if text.strip() else "") + block + "\n"


def sidebar(text: str, mutation: bool = False) -> str:
    # Two blocks, each one more item of a hand-written list (wiki/_Sidebar.md): the core's test pages
    # in the Quality section, the showcase's in the Testing showcase section. Each block sits
    # right after its list's last item; both markers are indented, so the Markdown keeps them inside
    # the list instead of ending it there and starting a second one.
    core = "\n".join(
        [
            START,
            "- [Test cases and runs](Tests)",
            *[f"  - [{SUITE_NAME[s]}]({p})" for s, p in SUITE_PAGE.items() if s != "selenium"],
            "  - [Obsolete](Tests-Obsolete)",
            "  " + END,
        ]
    )
    showcase = "\n".join(
        [
            SHOWCASE_START,
            f"- [Selenium cases]({SUITE_PAGE['selenium']})",
            "- [Runs](Tests-Runs)",
            *(["- [Mutation testing](Tests-Mutation)"] if mutation else []),
            "  " + SHOWCASE_END,
        ]
    )
    return _replace(_replace(text, START, END, core), SHOWCASE_START, SHOWCASE_END, showcase)


def generate(store: Path, out: Path, repo: str, last: int, window: int, root: Path = ROOT) -> list[str]:
    catalog, obsolete, runs = load(store, renamed_ids(root / "tests/catalog/renamed.toml"))
    mutation, history = load_mutation(store)
    mapping = load_mapping(root)
    pages = {
        "Tests": page_overview(repo, catalog, obsolete, runs, mutation, mapping),
        "Tests-Runs": page_runs(repo, runs),
        "Tests-Obsolete": page_obsolete(repo, obsolete),
    }
    for suite, name in SUITE_PAGE.items():
        pages[name] = page_suite(repo, suite, catalog, runs, last, window, mapping)
    svgs: dict[str, str] = {}
    if mutation is not None:
        pages["Tests-Mutation"], svgs = page_mutation(repo, mutation, history, root)
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("Tests-*.md"):
        if old.stem not in pages:
            old.unlink()
    for old in out.glob("tests-*.svg"):
        if old.name not in svgs:
            old.unlink()
    for name, text in pages.items():
        (out / f"{name}.md").write_text(text.rstrip() + "\n", encoding="utf-8", newline="\n")
    for name, text in svgs.items():
        (out / name).write_text(text, encoding="utf-8", newline="\n")
    sb = out / "_Sidebar.md"
    sb.write_text(
        sidebar(sb.read_text(encoding="utf-8") if sb.is_file() else "", mutation is not None),
        encoding="utf-8",
        newline="\n",
    )
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
