"""The wiki page Checks: every automatic check, generated on every wiki run. Never edited by hand.

    python -I tests/catalog/checks_page.py --out WIKI_DIR --repo OWNER/NAME [--rules RULES.json]

Writes `Checks.md` into WIKI_DIR, grouped by when each check runs: before a commit, on every change,
after integration, continuously, and at runtime (Böckeler's "keep quality left"). What each CI job,
showcase job, scheduled run and release step checks comes from the registry
`tests/catalog/checks.toml`; the rest is read from where it is defined, so it can't fall behind: the
jobs from `.github/workflows/tests.yml` and `showcase.yml`, the schedules from every workflow's
`schedule:`, the steps from `src/traceconomics/release.py`, the site
checks from the numbered header of `site/scripts/checks.mjs`, the repository checks from the test
files marked `repository`, the linters' settings from their configuration, the coverage floors from
the code that applies them.

It refuses to write the page while the registry and the sources disagree (`problems()`): a job or
step, showcase job or scheduled workflow with no entry, an entry for one that doesn't exist, a site
check number missing or repeated.
RULES is the JSON GitHub returns for the rules on main (`GET /repos/{owner}/{repo}/rules/branches/main`);
given it, the required checks in the registry must match the ones the rules require, or nothing is
written.

The same repository gives the same bytes. Standard library only.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = Path("tests/catalog/checks.toml")
WORKFLOW = Path(".github/workflows/tests.yml")
SHOWCASE = Path(".github/workflows/showcase.yml")
WORKFLOWS = Path(".github/workflows")
RELEASE = Path("src/traceconomics/release.py")
SITE_CHECKS = Path("site/scripts/checks.mjs")
PYPROJECT = Path("pyproject.toml")
PRETTIER = Path("site/.prettierrc.json")
ESLINT = Path("site/eslint.config.mjs")
STYLELINT = Path("site/stylelint.config.mjs")
HEAD = "> Generated, do not edit. Made from the repository on every wiki run (`tests/catalog/checks_page.py`); a correction goes into the check or into `tests/catalog/checks.toml`, and this page follows.\n"


def code(text: str) -> str:
    """Text safe inside a code span in a Markdown table cell."""
    return str(text).replace("|", "\\|").replace("\n", " ")


def prose(text: str) -> str:
    """Text read from a source, safe as Markdown: a tag it names (`<nav>`) stays text, not HTML.

    Code spans are left as they are: inside them the wiki shows `<` as typed.
    """
    parts = re.split(r"(`[^`]*`)", str(text))
    return "".join(part if i % 2 else part.replace("<", "&lt;") for i, part in enumerate(parts))


def esc(text: str) -> str:
    """Text safe inside a Markdown table cell."""
    return code(prose(text))


def registry(root: Path = ROOT) -> dict:
    """The registry, parsed."""
    return tomllib.loads((root / REGISTRY).read_text(encoding="utf-8"))


def ci_jobs(text: str) -> list[str]:
    """The job names of a workflow file, in order: the keys indented two spaces under `jobs:`."""
    out, inside = [], False
    for line in text.splitlines():
        if re.match(r"^\S", line):
            inside = line.rstrip() == "jobs:"
            continue
        m = re.match(r"^  ([A-Za-z0-9_-]+):\s*(#.*)?$", line)
        if inside and m:
            out.append(m.group(1))
    return out


def schedules(root: Path) -> dict[str, list[str]]:
    """Each workflow file with a `schedule:` under `on:`, and its cron lines, by file name."""
    out = {}
    for path in sorted((root / WORKFLOWS).glob("*.yml")):
        crons, on, sched = [], False, False
        for line in path.read_text(encoding="utf-8").splitlines():
            if re.match(r"^\S", line):
                on, sched = line.rstrip() == "on:", False
            elif on and re.match(r"^  \S", line):
                sched = line.strip().startswith("schedule:")
            elif sched and (m := re.match(r'^\s+- cron: "([^"]+)"', line)):
                crons.append(m.group(1))
        if crons:
            out[path.name] = crons
    return out


def release_steps(text: str) -> list[str]:
    """The build's steps, in order: the `Step("name", ...)` calls inside `def steps(` (a promote is a
    step of its own elsewhere in the file, not one of the build's)."""
    m = re.search(r"^def steps\(.*?(?=^def |\Z)", text, re.M | re.S)
    if not m:
        raise SystemExit(f"no `def steps(` in {RELEASE}")
    return re.findall(r'\bStep\(\s*"([^"]+)"', m.group(0))


def site_checks(text: str) -> list[tuple[int, str]]:
    """The numbered checks in the file's leading comment: (number, text), the text on one line."""
    out: list[tuple[int, str]] = []
    for line in text.splitlines():
        if not line.startswith("//"):
            break
        body = line[2:].strip()
        m = re.match(r"^(\d+)\.\s+(.*)$", body)
        if m:
            out.append((int(m.group(1)), m.group(2)))
        elif out and body:
            out[-1] = (out[-1][0], out[-1][1] + " " + body)
        elif out:
            out.append((0, ""))  # a blank comment line ends the list
    return [(n, t) for n, t in out if n]


def repository_tests(root: Path = ROOT) -> list[tuple[str, str]]:
    """The test files whose layer is `repository`: (path, the first sentence of their docstring)."""
    out = []
    for path in sorted((root / "tests").glob("test_*.py")):
        text = path.read_text(encoding="utf-8")
        if not re.search(r"^pytestmark = pytest\.mark\.repository\b", text, re.M):
            continue
        doc = ast.get_docstring(ast.parse(text)) or ""
        para = " ".join(doc.split("\n\n")[0].split())
        first = re.split(r"(?<=\.)\s", para, maxsplit=1)[0]  # the first sentence
        out.append((path.relative_to(root).as_posix(), first))
    return out


def floor(root: Path, spec: dict) -> str:
    """A coverage floor, read from the code that applies it."""
    m = re.search(spec["pattern"], (root / spec["file"]).read_text(encoding="utf-8"), re.M)
    if not m:
        raise SystemExit(f"no coverage floor in {spec['file']} (pattern {spec['pattern']!r})")
    value = float(m.group(1))
    return f"{value:g}%"


def style(root: Path = ROOT) -> list[tuple[str, str, str]]:
    """The formatters and linters: (tool, its settings in a few words, its configuration file)."""
    py = tomllib.loads((root / PYPROJECT).read_text(encoding="utf-8"))["tool"]["ruff"]
    rules = ", ".join(f"`{r}`" for r in py["lint"]["select"])
    out = [
        (
            "Ruff (Python)",
            f"formatter, width {py['line-length']}; linter, rule sets {rules}; target `{py['target-version']}`",
            PYPROJECT.as_posix(),
        )
    ]
    pr = json.loads((root / PRETTIER).read_text(encoding="utf-8"))
    plugins = ", ".join(f"`{p}`" for p in pr.get("plugins", []))
    out.append(
        (
            "Prettier (the site, Markdown, the wiki)",
            f"width {pr['printWidth']}" + (f"; plugins {plugins}" if plugins else ""),
            PRETTIER.as_posix(),
        )
    )
    text = (root / ESLINT).read_text(encoding="utf-8")
    packages = dict(re.findall(r'^import (\w+) from "([^"]+)";', text, re.M))
    sets = [f"`{packages.get(name, name)}` {kind}" for name, kind in re.findall(r"\b(\w+)\.configs\.(\w+)\b", text)]
    out.append(("ESLint (the site's code)", "rule sets " + ", ".join(sets), ESLINT.as_posix()))
    if (root / STYLELINT).is_file():
        text = (root / STYLELINT).read_text(encoding="utf-8")
        m = re.search(r"extends:\s*\[([^\]]*)\]", text)
        extends = re.findall(r'"([^"]+)"', m.group(1)) if m else []
        what = "extends " + ", ".join(f"`{e}`" for e in extends) if extends else "see its configuration"
        # Its own rules are described by the comment that opens the file: its first sentence.
        comment = re.match(r"(?://[^\n]*\n)+", text)
        if comment:
            lines = [re.sub(r"^//\s?", "", line).strip() for line in comment.group(0).splitlines()]
            para = " ".join(lines[: lines.index("")] if "" in lines else lines)
            first = re.split(r"(?<=\.)\s", para, maxsplit=1)[0].removeprefix("Stylelint: ")
            what += ". " + first[:1].upper() + first[1:]
        out.append(("Stylelint (the site's CSS)", what, STYLELINT.as_posix()))
    out.append(("Astro (types)", "`astro check`, in `npm run check`", "site/tsconfig.json"))
    return out


def problems(root: Path = ROOT, reg: dict | None = None) -> list[str]:
    """Where the registry and the sources disagree; empty when the page can be written."""
    reg = registry(root) if reg is None else reg
    out = []

    def same(kind: str, entries: list[dict], actual: list[str], where: Path) -> None:
        keys = [e["key"] for e in entries]
        for k in sorted({k for k in keys if keys.count(k) > 1}):
            out.append(f"{kind} {k!r} is listed twice in {REGISTRY}")
        for k in actual:
            if k not in keys:
                out.append(f"{kind} {k!r} in {where} has no entry in {REGISTRY}")
        for k in keys:
            if k not in actual:
                out.append(f"{kind} {k!r} in {REGISTRY} is not in {where}")

    same("job", reg.get("ci", []), ci_jobs((root / WORKFLOW).read_text(encoding="utf-8")), WORKFLOW)
    same("step", reg.get("release", []), release_steps((root / RELEASE).read_text(encoding="utf-8")), RELEASE)
    same("showcase job", reg.get("showcase", []), ci_jobs((root / SHOWCASE).read_text(encoding="utf-8")), SHOWCASE)
    same(
        "scheduled workflow",
        [{"key": e["workflow"]} for e in reg.get("scheduled", [])],
        list(schedules(root)),
        WORKFLOWS,
    )
    numbers = [n for n, _ in site_checks((root / SITE_CHECKS).read_text(encoding="utf-8"))]
    if numbers != list(range(1, len(numbers) + 1)):
        out.append(f"the site checks in {SITE_CHECKS}'s header are numbered {numbers}, not 1 to {len(numbers)}")
    for kind in ("inside", "continuous", "runtime"):
        for e in reg.get(kind, []):
            if not (root / e["where"]).exists():
                out.append(f"{kind} {e['name']!r} names {e['where']}, which doesn't exist")
    return out


def required_problems(reg: dict, rules: list[dict]) -> list[str]:
    """Where the registry's required checks differ from what the branch rules require."""
    contexts = sorted(
        c["context"]
        for r in rules
        if r.get("type") == "required_status_checks"
        for c in r.get("parameters", {}).get("required_status_checks", [])
    )
    scanning = any(r.get("type") == "code_scanning" for r in rules)
    ours = sorted(e["key"] for e in reg.get("ci", []) if e.get("required") is True)
    ours_scanning = any(e.get("required") == "code scanning" for e in reg.get("ci", []))
    out = []
    if contexts != ours:
        out.append(f"the rules on main require the checks {contexts}; {REGISTRY} says {ours}")
    if scanning != ours_scanning:
        out.append(
            f"the rules on main {'require' if scanning else 'do not require'} code scanning results; "
            f"{REGISTRY} says they {'do' if ours_scanning else 'do not'}"
        )
    return out


def page(root: Path, repo: str, reg: dict, rules_checked: bool) -> str:
    """The page's Markdown."""

    def src(path: str) -> str:
        return f"[`{path}`](https://github.com/{repo}/blob/main/{path})"

    def run(entry: dict) -> str:
        local = entry.get("local") or []
        return ", then ".join(f"`{code(c)}`" for c in ([local] if isinstance(local, str) else local)) or "–"

    def not_checks(entries: list[dict], key: str) -> list[str]:
        others = [f"`{e[key]}` ({esc(e['what'])})" for e in entries if e.get("check") is False]
        return ["", "Not a check: " + "; ".join(others)] if others else []

    lines = [
        HEAD,
        "# Checks",
        "",
        "Every check that runs by itself, what it proves, what stops when it fails, and how to run it "
        "first. In the terms of [Harness engineering](Harness-engineering), each one is a computational "
        "sensor: it observes a change after it is made, and gives the same answer every time. They are "
        'grouped by when they run, cheapest and earliest first, as Böckeler\'s "keep quality left" asks. '
        "A **gate** is a place where a failed sensor blocks something: a merge, a release build, a "
        "promotion. [Rules: guides and sensors](Rules-guides-and-sensors) says which of them enforce each "
        "hard rule; [Test strategy](Test-strategy) says what each test level proves; the "
        "[test pages](Tests) list every test case.",
        "",
        "## Before a commit",
        "",
        "Nothing runs by itself before a commit: the repository has no commit hook. Every check below with a "
        'command under "Run it first" runs the same way locally, and `AGENTS.md`\'s definition of done says '
        "which to run for which change. The formatters are run before a commit to rewrite the code, not "
        "only to check it.",
        "",
        "## On every change",
        "",
        f"The pipeline ({src(WORKFLOW.as_posix())}) runs these jobs side by side on every push and pull "
        "request. A pull request merges only when the required ones pass "
        + (
            "(checked against the branch rules on `main` when this page was made)."
            if rules_checked
            else "(as recorded in the registry; the branch rules on `main` are the authority)."
        )
        + " A job that isn't required still turns the run red.",
        "",
        "| Job | Required | What it checks | Run it first |",
        "| --- | --- | --- | --- |",
    ]
    for e in reg["ci"]:
        if e.get("check") is False:
            continue
        req = (
            "code scanning results" if e.get("required") == "code scanning" else ("yes" if e.get("required") else "no")
        )
        lines.append(f"| `{e['key']}`: {esc(e['name'])} | {req} | {esc(e['what'])} | {run(e)} |")
    lines += not_checks(reg["ci"], "key")

    lines += ["", "### Code style", "", "| Tool | Settings | Configuration |", "| --- | --- | --- |"]
    lines += [f"| {tool} | {esc(what)} | {src(cfg)} |" for tool, what, cfg in style(root)]
    lines += [
        "",
        "Nobody formats by hand; a rule switched off for one line names its reason on that line.",
        "",
        "### Site checks",
        "",
        f"Run after every build ({src(SITE_CHECKS.as_posix())}): in the `site` job, in each data state, and in "
        "the release step `site-check`. Each failure is listed; any one fails the run.",
        "",
    ]
    lines += [f"{n}. {prose(t)}" for n, t in site_checks((root / SITE_CHECKS).read_text(encoding="utf-8"))]
    lines += [
        "",
        "### Repository checks",
        "",
        "pytest tests of the repository's own files (layer `repository`), in the `python` job.",
        "",
        "| File | What it checks |",
        "| --- | --- |",
    ]
    lines += [f"| {src(path)} | {esc(doc)} |" for path, doc in repository_tests(root)]
    lines += ["", "### Checks inside the runs", "", "| Check | What fails | Where |", "| --- | --- | --- |"]
    for g in reg.get("inside", []):
        what = g["what"] + (f" Floor: {floor(root, g['floor'])}." if "floor" in g else "")
        lines.append(f"| {esc(g['name'])} | {esc(what)} | {src(g['where'])} |")

    lines += [
        "",
        "## After integration",
        "",
        f"The [testing showcase](Testing-showcase) ({src(SHOWCASE.as_posix())}) runs after the pipeline on "
        "`main`, or by hand: the slower and more expensive sensors. Never on a pull request, never a "
        "required check or a release step.",
        "",
        "| Job | When | What it checks |",
        "| --- | --- | --- |",
    ]
    lines += [
        f"| `{e['key']}`: {esc(e['name'])} | {esc(e['when'])} | {esc(e['what'])} |"
        for e in reg.get("showcase", [])
        if e.get("check") is not False
    ]
    lines += not_checks(reg.get("showcase", []), "key")

    crons = schedules(root)
    lines += [
        "",
        "## Continuous",
        "",
        "Sensors on a timer, outside any change: they catch what drifts while nobody touches the code.",
        "",
        "| Workflow | Schedule (UTC, cron) | What it checks |",
        "| --- | --- | --- |",
    ]
    lines += [
        f"| {src((WORKFLOWS / e['workflow']).as_posix())} | {', '.join(f'`{c}`' for c in crons[e['workflow']])} "
        f"| {esc(e['what'])} |"
        for e in reg.get("scheduled", [])
        if e.get("check") is not False and e["workflow"] in crons
    ]
    lines += not_checks(reg.get("scheduled", []), "workflow")
    lines += ["", "| Check | When | What it checks | Where |", "| --- | --- | --- | --- |"]
    lines += [
        f"| {esc(a['name'])} | {esc(a['when'])} | {esc(a['what'])} | {src(a['where'])} |"
        for a in reg.get("continuous", [])
    ]

    lines += [
        "",
        "## Runtime",
        "",
        "### In a release build",
        "",
        f"The release server runs these steps in order ({src(RELEASE.as_posix())}). A step that fails stops "
        "the build there and the owner gets an alert naming it; nothing reaches the live site without every "
        "step passing, and a person or the automatic-promotion rules decide whether it goes live.",
        "",
        "| # | Step | Kind | What it does | Run it first |",
        "| --- | --- | --- | --- | --- |",
    ]
    for i, e in enumerate(reg["release"], 1):
        kind = "build" if e.get("check") is False else "check"
        lines.append(f"| {i} | `{e['key']}`: {esc(e['name'])} | {kind} | {esc(e['what'])} | {run(e)} |")
    lines += ["", "### On the live site", "", "| Check | When | What it checks | Where |", "| --- | --- | --- | --- |"]
    lines += [
        f"| {esc(a['name'])} | {esc(a['when'])} | {esc(a['what'])} | {src(a['where'])} |"
        for a in reg.get("runtime", [])
    ]
    return "\n".join(lines)


def generate(out: Path, repo: str, rules: list[dict] | None = None, root: Path | None = None) -> list[str]:
    """Write `Checks.md` into `out`; refuse (SystemExit) while the registry and the sources disagree."""
    root = ROOT if root is None else root
    reg = registry(root)
    found = problems(root, reg) + (required_problems(reg, rules) if rules is not None else [])
    if found:
        raise SystemExit("Checks page not written:\n  " + "\n  ".join(found))
    out.mkdir(parents=True, exist_ok=True)
    text = page(root, repo, reg, rules is not None)
    (out / "Checks.md").write_text(text.rstrip() + "\n", encoding="utf-8", newline="\n")
    return ["Checks"]


def main(argv=None):
    """The command line."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--rules", type=Path, help="GitHub's JSON for the rules on main")
    a = ap.parse_args(argv)
    rules = json.loads(a.rules.read_text(encoding="utf-8")) if a.rules else None
    print("wrote " + ", ".join(generate(a.out, a.repo, rules)))


if __name__ == "__main__":
    sys.exit(main())
