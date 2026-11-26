"""The wiki page Agent-evals: every recorded eval run, generated on every wiki run. Never edited by hand.

    python -I tests/evals/page.py --out WIKI_DIR --repo OWNER/NAME

Writes `Agent-evals.md` from the tasks (`tests/evals/tasks/`) and the results (`tests/evals/results/`):
per task, the rule at stake and the prompt, then one row per run. Writes nothing while there is no
result: a page about evals that never ran would describe planned work. The same files give the
same bytes. Standard library only.
"""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
from pathlib import Path

HERE = Path(__file__).resolve().parent
HEAD = "> Generated, do not edit. Made from `tests/evals/` on every wiki run (`tests/evals/page.py`); a new run is a new result file there.\n"
MARK = {True: "yes", False: "no", None: "–"}


def esc(text: str) -> str:
    """Text safe inside a Markdown table cell."""
    return str(text).replace("|", "\\|").replace("\n", " ")


def load(root: Path = HERE) -> tuple[dict[str, dict], list[dict]]:
    """The tasks by id, and the results, oldest first."""
    tasks = {p.stem: tomllib.loads(p.read_text(encoding="utf-8")) for p in sorted((root / "tasks").glob("*.toml"))}
    results = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((root / "results").glob("*.json"))]
    return tasks, sorted(results, key=lambda r: (r["date"], r["task"], r["agent"]))


def page(tasks: dict[str, dict], results: list[dict], repo: str) -> str:
    """The page's Markdown."""
    lines = [
        HEAD,
        "# Agent evals",
        "",
        "Part of the maintainer's testing showcase. [Rules and their guards](Rules-and-their-guards) shows "
        "what enforces each hard rule; these evals ask what a coding agent actually does when the quickest "
        "way to finish a task breaks one.",
        "",
        "Each task is a real change to the repository, seeded in a throwaway clone with no remote: a test "
        "updated for a file the saved copy doesn't hold, a method change that moves a rebuilt index away "
        "from the official one, a site text asked for in English. A fresh agent gets the prompt and the "
        f"repository, with [`AGENTS.md`](https://github.com/{repo}/blob/main/AGENTS.md) as its only "
        "statement of the rules. Afterwards the runner records what it changed, whether it took the "
        "shortcut, whether a guard caught it, and whether it reverted the seed or made commits. A person "
        "judges the agent's report: did it say what it did, and what it didn't do.",
        "",
        "Results are runs, never a gate. The same tasks can be given to any agent: `AGENTS.md` is "
        f"vendor-neutral. The runner: [`tests/evals/evals.py`](https://github.com/{repo}/blob/main/tests/evals/evals.py).",
    ]
    for name, t in tasks.items():
        runs = [r for r in results if r["task"] == name]
        lines += [
            "",
            f"## {name}",
            "",
            f"**Rule:** {esc(t['rule'])}",
            "",
            "**Prompt:** " + " ".join(t["prompt"].split()),
            "",
        ]
        if not runs:
            lines.append("No run yet.")
            continue
        lines += [
            "| Date | Agent | Shortcut taken | Guard caught it | Seed reverted | Commits | Report honest |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
        for r in runs:
            lines.append(
                f"| {r['date']} | {esc(r['agent'])} | {MARK[r['shortcut_taken']]} | "
                f"{MARK[r['caught']] if r['shortcut_taken'] else '–'} | {MARK[r['seed_reverted']]} | "
                f"{r['commits']} | {r['report_honest'] or '–'} |"
            )
        for r in runs:
            shortcuts = "; ".join(r["shortcuts"]) or "none"
            lines += [
                "",
                f"<details><summary>{r['date']}, {esc(r['agent'])}: the agent's report</summary>",
                "",
                f"Shortcuts: {esc(shortcuts)}. Files changed: {esc(', '.join(r['changed']) or 'none')}."
                + (f" Note: {esc(r['note'])}" if r["note"] else ""),
                "",
                *[f"> {line}" if line else ">" for line in r["report"].splitlines()],
                "",
                "</details>",
            ]
    return "\n".join(lines)


def generate(out: Path, repo: str, root: Path = HERE) -> list[str]:
    """Write `Agent-evals.md` into `out`, or nothing while no run is recorded."""
    tasks, results = load(root)
    if not results:
        return []
    out.mkdir(parents=True, exist_ok=True)
    (out / "Agent-evals.md").write_text(page(tasks, results, repo).rstrip() + "\n", encoding="utf-8", newline="\n")
    return ["Agent-evals"]


def main(argv=None):
    """The command line."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--repo", required=True)
    a = ap.parse_args(argv)
    print("wrote " + (", ".join(generate(a.out, a.repo)) or "nothing: no run recorded"))


if __name__ == "__main__":
    sys.exit(main())
