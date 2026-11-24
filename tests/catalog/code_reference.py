"""The wiki's code reference, generated from the package's docstrings. Never edited by hand.

    python -I tests/catalog/code_reference.py --src src/traceconomics --out WIKI_DIR --repo OWNER/NAME --commit SHA \
        [--store DIR]

Reads the package with `ast` (nothing is imported or run) and writes:

    Code.md               the overview: every package, what it is for, its modules
    Code-<package>.md     one page per package: each module's docstring, then its public functions,
                          classes and methods with their first lines, each linked to its source line
    _Sidebar.md           only the block between `<!-- code:start -->` and `<!-- code:end -->`

and removes any other `Code-*.md` it wrote before. Every page starts with "Generated, do not edit"
and names the commit it was made from; the source links point at that commit, so they stay right
when the code moves on. Public means what tests/test_docstrings.py checks: no leading underscore.
The top-level modules (`cli.py`, `job.py`, ...) are one page, `Code-top-level`.

With `--store` (the branch `test-history`), the pages also show what the tests run, from its
`code-map.json` (tests/coverage/code_map.py) joined to its `catalog.json`: each module's lines by
the lowest layer of test that runs them, the lines no test runs, and the test cases that run it,
linked to their steps on the Tests pages; each public member's tests, or "imported only" (it was
defined while a test file was loaded, but no test ran it), or "no test". `Code.md` adds the
repository's own checks (the `repository` layer, which runs no package code), the unit and
integration tests that run no package code, and any test run without a case. The map can be older
than the commit the pages are made from; the pages name both.

With a stored `mutation.json` (tests/coverage/mutation.py), `Code-engine` ends with the mutation
testing result: the score, and each survivor with its change and, when it behaves the same as the
code, the reason from tests/coverage/mutation-equivalent.toml. It says so when the engine's source
has changed since the run.

Standard library only. The same source and commit give the same bytes.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import sys
import tomllib
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # run with `python -I`: its folder isn't on the path
import code_charts as charts  # noqa: E402

HEAD = (
    "> Generated, do not edit. Made from the code's docstrings on every update of the wiki; a correction "
    "goes into the docstring, and this page follows.\n"
)
START, END = "<!-- code:start -->", "<!-- code:end -->"
TOP = "top-level"  # the page name of the modules directly in the package
INDENT = 4  # docstring lines indented this much are code (formulas, layouts); lists nest by 2
LAYERS = ("unit", "integration")  # the layers that run package code, the lowest first
SITE_LAYERS = ("unit", "integration", "e2e")  # the front-end badge's layers
BACK_STATUSES = ("unit", "integration", "imported", "none")
SITE_STATUSES = ("unit", "integration", "e2e", "none")
TESTS_PAGE = "Tests-pytest"
SITE = "site"  # the front end's page, Code-site
MEANS = {
    "unit": "a unit test runs it directly (pytest, or Vitest's unit files)",
    "integration": "only tests that run it with its real neighbours: files on disk, the store, the generated data",
    "e2e": "front end only: only Playwright reaches it, through the built site",
    "imported": "back end only: it ran only while test files were being loaded (imports, `def` lines)",
    "none": "no test runs it",
}
COLOUR = {"unit": "blue", "integration": "orange", "e2e": "green", "imported": "dark grey", "none": "light grey"}


@dataclass
class Coverage:
    """What the tests run, from the stored code map, with each test joined to its case."""

    commit: str
    modules: dict  # path -> the map's entry (tests/coverage/code_map.py)
    tests: list[str]  # node IDs; the map's entries refer to them by position
    cases: dict  # node ID -> the catalog's pytest case
    catalog: list[dict]  # every pytest case
    front: dict | None = None  # the map's front end: its tests and files
    others: list[dict] = field(default_factory=list)  # the Vitest, Playwright and Selenium cases

    @staticmethod
    def load(store: Path) -> Coverage | None:
        """The map and catalog stored in `store`, or None when there is no map yet."""
        if not (store / "code-map.json").is_file():
            return None
        m = json.loads((store / "code-map.json").read_text(encoding="utf-8"))
        cat = store / "catalog.json"
        cases = json.loads(cat.read_text(encoding="utf-8"))["cases"] if cat.is_file() else []
        pytest_cases = [c for c in cases if c["suite"] == "pytest" and c.get("id")]
        others = [c for c in cases if c["suite"] != "pytest" and c.get("id")]
        back = m["back-end"]
        nodes = {c["node"]: c for c in pytest_cases}
        return Coverage(m["commit"], back["modules"], back["tests"], nodes, pytest_cases, m.get("front-end"), others)

    def front_link(self, key: str) -> list[str]:
        """A front-end test as links to its cases: a Vitest file's every case, a Playwright case, a Selenium test's."""
        kind, _, name = key.partition("|")
        if kind == "vitest":
            found = [c for c in self.others if c["suite"] == "vitest" and c["file"] == f"site/{name}"]
            head = f"`{name}`: "
        elif kind == "playwright":
            found = [c for c in self.others if c["suite"] == "playwright" and c["id"] == name]
            head = ""
        else:
            found = [c for c in self.others if c["suite"] == "selenium" and c["node"] == name]
            head = ""
        if not found:
            return [f"`{name}` (no case)"]
        page = {"vitest": "Tests-Vitest", "playwright": "Tests-Playwright", "selenium": "Tests-Selenium"}[kind]
        links = [
            f"[{c['id']}]({page}#{c['id'].lower()}) {inline(c['title'])}" for c in sorted(found, key=lambda c: c["id"])
        ]
        return [head + ", ".join(links)] if kind == "vitest" else links

    def case_link(self, node: str) -> str:
        """A test as a link to its case's steps, or its node ID when it has no case."""
        c = self.cases.get(node)
        if c is None:
            return f"`{node}` (no case)"
        return f"[{c['id']}]({TESTS_PAGE}#{c['id'].lower()}) {inline(c['title'])}"

    def sort_key(self, node: str) -> tuple:
        c = self.cases.get(node)
        return (c is None, c["id"] if c else node)


@dataclass
class Member:
    """One public function, class or method: its name, kind, signature, source line and docstring."""

    name: str
    kind: str  # "function", "class" or "method"
    signature: str
    line: int
    doc: str
    members: list[Member] = field(default_factory=list)


@dataclass
class Module:
    """One module: its dotted name, file, docstring and public members, in source order."""

    name: str
    path: str  # relative to the repository root
    doc: str
    members: list[Member]


def first_line(doc: str) -> str:
    """The docstring's first line, or an empty string."""
    lines = doc.strip().splitlines()
    return lines[0].strip() if lines else ""


def signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """The argument list as written in the source, without annotations or defaults."""
    a = node.args
    parts = [p.arg for p in a.posonlyargs]
    if a.posonlyargs:
        parts.append("/")
    parts += [p.arg for p in a.args]
    if a.vararg:
        parts.append("*" + a.vararg.arg)
    elif a.kwonlyargs:
        parts.append("*")
    parts += [p.arg for p in a.kwonlyargs]
    if a.kwarg:
        parts.append("**" + a.kwarg.arg)
    if parts and parts[0] in ("self", "cls"):
        parts = parts[1:]
    return "(" + ", ".join(parts) + ")"


def read_module(path: Path, src: Path, root: Path) -> Module:
    """One module's docstring and public members, from its source."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    rel = path.relative_to(src)
    dotted = ".".join((src.name, *rel.with_suffix("").parts)).removesuffix(".__init__")
    members = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and not node.name.startswith("_"):
            members.append(Member(node.name, "function", signature(node), node.lineno, ast.get_docstring(node) or ""))
        elif isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
            methods = [
                Member(m.name, "method", signature(m), m.lineno, ast.get_docstring(m) or "")
                for m in node.body
                if isinstance(m, ast.FunctionDef | ast.AsyncFunctionDef) and not m.name.startswith("_")
            ]
            members.append(Member(node.name, "class", "", node.lineno, ast.get_docstring(node) or "", methods))
    return Module(dotted, path.relative_to(root).as_posix(), ast.get_docstring(tree) or "", members)


def packages(src: Path, root: Path) -> dict[str, list[Module]]:
    """Every module by page: `top-level` for the modules directly in the package, else the first folder."""
    out: dict[str, list[Module]] = {}
    for path in sorted(src.rglob("*.py"), key=lambda p: p.relative_to(src).as_posix()):
        rel = path.relative_to(src)
        page = TOP if len(rel.parts) == 1 else rel.parts[0]
        out.setdefault(page, []).append(read_module(path, src, root))
    return dict(sorted(out.items(), key=lambda kv: (kv[0] != TOP, kv[0])))


CODE_SPAN = re.compile(r"(`[^`]*`)")


def inline(text: str) -> str:
    """Docstring text made safe for Markdown: code spans kept, `<`, `>`, `*` and `_` escaped elsewhere."""
    parts = CODE_SPAN.split(text)
    for i in range(0, len(parts), 2):  # the even parts are outside code spans
        p = parts[i].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        parts[i] = re.sub(r"([*_\\])", r"\\\1", p)
    return "".join(parts)


def render(doc: str) -> str:
    """A docstring as Markdown: text and lists as they are, an indented block after a blank line as code.

    `ast.get_docstring` has already removed the common indentation, so text starts at column 0 and
    list items nest by 2; a block indented 4 or more after a blank line (a formula, a folder layout)
    is code, kept exactly.
    """
    out: list[str] = []
    code: list[str] = []

    def flush():
        while code and not code[-1].strip():
            code.pop()
        if code:
            if out and out[-1]:
                out.append("")
            out.extend(["```text", *code, "```", ""])
            code.clear()

    previous_blank = True
    for line in doc.strip("\n").splitlines():
        indent = len(line) - len(line.lstrip())
        # A block starts only after a blank line, as in Markdown: an indented line right under text
        # is that text wrapping (a list item's continuation), not code.
        if line.strip() and indent >= INDENT and (code or previous_blank) or code and not line.strip():
            code.append(line[INDENT:] if indent >= INDENT else "")
        else:
            flush()
            out.append(" " * min(indent, 2) + inline(line.strip()) if line.strip() else "")
        previous_blank = not line.strip()
    flush()
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()


def source_link(repo: str, commit: str, path: str, line: int | None = None) -> str:
    """A link to a file, or a line in it, at the commit the page was made from."""
    url = f"https://github.com/{repo}/blob/{commit}/{path}"
    return url + (f"#L{line}" if line else "")


def commit_link(repo: str, commit: str) -> str:
    """A link to the commit the pages were made from."""
    return f"https://github.com/{repo}/commit/{commit}"


def page_title(page: str) -> str:
    """The page's heading name: `Top-level modules`, or the package's dotted name."""
    return "Top-level modules" if page == TOP else f"`traceconomics.{page}`"


def anchor(name: str) -> str:
    """GitHub's heading anchor for a heading that is just a code span: lower case, dots dropped."""
    return re.sub(r"[^a-z0-9_ -]", "", name.lower()).replace(" ", "-")


def member_tests(entry: dict | None) -> str:
    """A member's tests in a few words: how many of each layer, else "imported only" or "no test".

    Nothing when every line ran on import: a class made only of definitions (a dataclass's fields)
    has nothing a test could run, so "imported only" would wrongly say it is unused.
    """
    if entry is None or entry["lines"] == 0:
        return ""
    counts = [f"{k} {len(entry['tests'][k])}" for k in LAYERS if entry["tests"][k]]
    if counts:
        return " · tests: " + ", ".join(counts)
    if entry["none"] == 0:
        return ""
    return " · **imported only**" if entry["imported"] else " · **no test**"


def line_ranges(ranges: list[list[int]], repo: str, commit: str, path: str) -> str:
    """Line ranges as links to the source at the map's commit: `12–14`, `40`."""
    out = []
    for a, b in ranges:
        text, frag = (f"{a}", f"L{a}") if a == b else (f"{a}–{b}", f"L{a}-L{b}")
        out.append(f"[{text}]({source_link(repo, commit, path)}#{frag})")
    return ", ".join(out)


def module_tests(entry: dict | None, cov: Coverage, repo: str, path: str) -> list[str]:
    """A module's lines by status and the cases that run it, folded away under a summary line."""
    if entry is None:
        return ["_Not in the coverage run yet: the module is newer than the code map._\n"]
    if entry["lines"] == 0:
        return ["_No lines with code._\n"]
    parts = [f"run by {k} tests {entry[k]}" if k == "unit" else f"by {k} tests only {entry[k]}" for k in LAYERS]
    line = f"**Tests:** {entry['lines']} lines with code: " + ", ".join(parts) + f", imported only {entry['imported']}"
    line += f", no test {entry['none']}"
    if entry["no_test"]:
        line += f" (lines {line_ranges(entry['no_test'], repo, cov.commit, path)})"
    out = [line + ".\n"]
    nodes = {k: sorted((cov.tests[i] for i in entry["tests"][k]), key=cov.sort_key) for k in LAYERS}
    if any(nodes.values()):
        summary = ", ".join(f"{k} {len(v)}" for k, v in nodes.items() if v)
        out.append(f"<details><summary>Test cases that run it: {summary}</summary>\n")
        for k, v in nodes.items():
            if v:
                out.append(f"{k.capitalize()}:\n")
                out += [f"- {cov.case_link(n)}" for n in v]
                out.append("")
        out.append("</details>\n")
    return out


def coverage_note(cov: Coverage | None, repo: str, commit: str) -> str:
    """The line that says which run the tests' figures come from."""
    if cov is None:
        return ""
    note = f"What the tests run comes from the coverage of commit [`{cov.commit[:7]}`]({commit_link(repo, cov.commit)})"
    if cov.commit != commit:
        note += ", an earlier commit than this page's: the code may have moved since"
    return note + ". A test that runs a line doesn't always check it.\n"


EQUIVALENT = "tests/coverage/mutation-equivalent.toml"


def engine_fingerprint(root: Path) -> dict[str, str]:
    """Each engine file's SHA-256, line endings made LF: as tests/coverage/mutation.py records it."""
    engine = root / "src" / "traceconomics" / "engine"
    return {
        p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
        for p in sorted(engine.rglob("*.py"))
    }


def equivalent_reason(survivor: dict, known: list[dict]) -> str | None:
    """The written reason a survivor behaves the same as the code, when it is listed (whitespace ignored)."""

    def norm(lines):
        return [re.sub(r"\s+", " ", line).strip() for line in lines]

    for e in known:
        if e["function"] == survivor["function"] and norm(e["change"]) == norm(survivor["change"]):
            return e["reason"].strip()
    return None


def mutation_section(result: dict, root: Path, repo: str) -> list[str]:
    """The engine page's mutation testing in brief, with a link to its own page (Tests-Mutation, tests/catalog/wiki.py)."""
    path = root / EQUIVALENT
    known = tomllib.loads(path.read_text(encoding="utf-8")).get("equivalent", []) if path.is_file() else []
    survivors = result["survivors"]
    gaps = sum(equivalent_reason(sv, known) is None for sv in survivors)
    score = "–" if result["score"] is None else f"{result['score']}%"
    when = f"on {result['started'][:10]} " if result.get("started") else ""
    line = (
        f"**{score}** of {result['mutants']} changes to the engine's code killed by its tests, {when}(commit "
        f"[`{result['commit'][:7]}`]({commit_link(repo, result['commit'])})); "
        + (f"{len(survivors)} survived, {gaps} not explained yet." if survivors else "none survived.")
        + " Every change, every survivor and the score over time: [Mutation testing](Tests-Mutation)."
    )
    out = ["## Mutation testing\n", line + "\n"]
    if result.get("source") != engine_fingerprint(root):
        out.append("> The engine's code has changed since this run: the result may no longer hold.\n")
    return out


def page_package(
    page: str,
    modules: list[Module],
    repo: str,
    commit: str,
    cov: Coverage | None = None,
    mutation: dict | None = None,
    root: Path | None = None,
) -> str:
    """One package's page: each module's docstring and its public members, linked to their source lines."""
    out = [
        f"# {page_title(page)}\n",
        HEAD,
        f"Made from commit [`{commit[:7]}`]({commit_link(repo, commit)}).\n",
    ]
    if cov is not None:
        out.append(coverage_note(cov, repo, commit))
    out.append("[Code reference](Code) · " + " · ".join(f"[`{m.name}`](#{anchor(m.name)})" for m in modules) + "\n")
    if cov is not None:
        rows = [(module_label(m), cov.modules[m.path]) for m in modules if cov.modules.get(m.path, {}).get("lines")]
        if rows:
            stem = f"code-map-{page}"
            out.append(charts.picture(stem, f"Stacked bars: the lines of each module of {page}, by status") + "\n")
            out.append(status_table(rows, BACK_STATUSES, "Module") + "\n")
    for m in modules:
        entry = cov.modules.get(m.path) if cov else None
        found = (entry or {}).get("members", {})
        out.append(f"## `{m.name}`\n")
        out.append(f"[{m.path}]({source_link(repo, commit, m.path)})\n")
        if m.doc:
            out.append(render(m.doc) + "\n")
        for mem in m.members:
            label = f"`{mem.name}{mem.signature}`" if mem.kind == "function" else f"class `{mem.name}`"
            out.append(
                f"- {label} ([source]({source_link(repo, commit, m.path, mem.line)})): {inline(first_line(mem.doc))}"
                + (member_tests(found.get(mem.name)) if cov else "")
            )
            for meth in mem.members:
                out.append(
                    f"  - `{meth.name}{meth.signature}` ([source]({source_link(repo, commit, m.path, meth.line)})): "
                    f"{inline(first_line(meth.doc))}"
                    + (member_tests(found.get(f"{mem.name}.{meth.name}")) if cov else "")
                )
        if m.members:
            out.append("")
        if cov is not None:
            out += module_tests(entry, cov, repo, m.path)
    if mutation is not None and page == "engine" and root is not None:
        out += mutation_section(mutation, root, repo)
    return "\n".join(out).rstrip() + "\n"


def page_overview(pages: dict[str, list[Module]], repo: str, commit: str, cov: Coverage | None = None) -> str:
    """The overview: one row per package, with what it is for and how many modules and public members it has."""
    out = [
        "# Code reference\n",
        HEAD,
        f"Made from commit [`{commit[:7]}`]({commit_link(repo, commit)}). Every module of the "
        "`traceconomics` package, with what its docstrings say. A page per package lists each module's "
        "docstring and its public functions and classes, each linked to its source line at that commit. "
        "Only what has no leading underscore is listed; the tests require a docstring on all of it.\n",
    ]
    if cov is not None:
        out.append(coverage_note(cov, repo, commit))
        out.append(
            "A line is *run by a test* when a test's own work runs it. Lines that run only while the tests "
            "are being loaded (imports, `def` and `class` lines, constants) are *imported only*: the "
            "README's coverage badge counts those as covered, so its figure is higher.\n"
        )
        out += [
            "| Package | What it is for | Modules | Public functions, classes and methods "
            "| Lines with code | Run by a test | Imported only | No test |",
            "|---|---|--:|--:|--:|--:|--:|--:|",
        ]
    else:
        out += [
            "| Package | What it is for | Modules | Public functions, classes and methods |",
            "|---|---|--:|--:|",
        ]
    for page, modules in pages.items():
        init = next((m for m in modules if m.name == f"traceconomics.{page}"), None)
        about = (
            first_line(init.doc)
            if init
            else "The modules directly in the package: the command line, the job, releases."
        )
        count = sum(len(m.members) + sum(len(x.members) for x in m.members) for m in modules)
        row = f"| [{page_title(page)}](Code-{page}) | {inline(about)} | {len(modules)} | {count} |"
        if cov is not None:
            entries = [cov.modules[m.path] for m in modules if m.path in cov.modules]
            lines = sum(e["lines"] for e in entries)
            counts = [sum(e[k] for e in entries for k in group) for group in (LAYERS, ("imported",), ("none",))]
            row += (
                f" {lines:,} | "
                + " | ".join(f"{n:,}" + (f" ({share(n, lines)})" if lines else "") for n in counts)
                + " |"
            )
        out.append(row)
    if cov is not None:
        if cov.front is not None:
            out.append(f"\nThe site's own code, file by file: [Front end (site)](Code-{SITE}).")
        out += overview_map(pages, cov)
        out += overview_tests(cov)
    return "\n".join(out) + "\n"


def module_label(m: Module) -> str:
    """A module's name within its package: `chain.py`, `elstat/parse.py`; the top level's by file name."""
    parts = m.path.split("/")[2:]  # after src/traceconomics
    return "/".join(parts[1:]) if len(parts) > 1 else parts[0]


def status_table(rows: list[tuple[str, dict]], statuses: tuple[str, ...], first: str) -> str:
    """The numbers under a bar chart: each row's lines, and each status's share of them."""
    out = [f"| {first} | Lines | " + " | ".join(statuses) + " |", "|---|--:|" + "--:|" * len(statuses)]
    for label, e in rows:
        out.append(
            f"| {inline(label)} | {e['lines']:,} | "
            + " | ".join(charts.share(e[k], e["lines"]) if e.get(k) else "" for k in statuses)
            + " |"
        )
    return "\n".join(out)


def summed(entries: list[dict], statuses: tuple[str, ...]) -> dict:
    """Several entries' lines and statuses added up, with the lines each suite or layer runs."""
    out = {"lines": sum(e["lines"] for e in entries), **{k: sum(e[k] for e in entries) for k in statuses}}
    ran: dict = {}
    for e in entries:
        for k, v in e.get("ran", {}).items():
            ran[k] = None if v is None or ran.get(k, 0) is None else ran.get(k, 0) + v
    out["ran"] = ran
    return out


def site_area(path: str) -> str:
    """A front-end file's folder on the map: `lib`, `lib/engine`, `scripts`, `pages`, …"""
    parts = path.split("/")
    return f"lib/{parts[2]}" if parts[1] == "lib" and len(parts) > 3 else parts[1]


def site_areas(front: dict) -> dict[str, list[tuple[str, dict]]]:
    """The front end's files by folder, the biggest folder first, each folder's files by size."""
    areas = defaultdict(list)
    for f, e in front["files"].items():
        areas[site_area(f)].append((f, e))
    for files in areas.values():
        files.sort(key=lambda fe: (-fe[1]["lines"], fe[0]))
    return dict(sorted(areas.items(), key=lambda kv: (-sum(e["lines"] for _, e in kv[1]), kv[0])))


def shares(entry: dict, cols: dict[str, str]) -> dict:
    """{column: the share of the entry's lines that suite runs}, None where it wasn't measured."""
    ran = entry["ran"]
    return {
        col: None if ran.get(key) is None or not entry["lines"] else ran[key] / entry["lines"]
        for col, key in cols.items()
    }


BACK_COLS = {"pytest unit": "unit", "pytest integration": "integration"}
SITE_COLS = {"Vitest unit": "unit", "Vitest integration": "integration", "Playwright": "e2e", "Selenium": "selenium"}


def heat_table(rows: list[tuple[str, dict]], cols: list[str], first: str) -> str:
    """The numbers under a heatmap."""
    out = [f"| {first} | " + " | ".join(cols) + " |", "|---|" + "--:|" * len(cols)]
    for label, sh in rows:
        cells = ["–" if v is None else ("<1%" if 0 < v < 0.005 else f"{100 * v:.0f}%") for v in sh.values()]
        out.append(f"| {inline(label)} | " + " | ".join(cells) + " |")
    return "\n".join(out)


def overview_map(pages: dict[str, list[Module]], cov: Coverage) -> list[str]:
    """The map on Code.md: the legend, the lines per area by status, which suites run each area."""
    back = {
        page: summed([cov.modules[m.path] for m in mods if m.path in cov.modules], BACK_STATUSES)
        for page, mods in pages.items()
    }
    back = {p: e for p, e in back.items() if e["lines"]}
    front = (
        {a: summed([e for _, e in fs], SITE_STATUSES) for a, fs in site_areas(cov.front).items()} if cov.front else {}
    )
    out = ["", "## The map\n"]
    out.append(
        "Each line with code counts once, for the first of these that holds (the README's coverage "
        "badges count the same way, except that they count *imported* lines for the layer of the file "
        "being loaded):\n"
    )
    out += ["| Status | Colour | The line |", "|---|---|---|"]
    out += [f"| **{k}** | {COLOUR[k]} | {MEANS[k]} |" for k in ("unit", "integration", "e2e", "imported", "none")]
    out.append(
        "\nThe Selenium suite tests the same pages as Playwright with another tool, so it isn't one of "
        "the layers; it has its own column below. The charts' numbers are in the table under each one.\n"
    )
    out.append("### Lines per area\n")
    out.append(
        charts.picture("code-map-overview", "Stacked bars: the lines of each area of the code, by status") + "\n"
    )
    out.append(status_table([(page_title(p).strip("`"), e) for p, e in back.items()], BACK_STATUSES, "Back end") + "\n")
    if front:
        out.append(status_table([(a, e) for a, e in front.items()], SITE_STATUSES, "Front end") + "\n")
    out.append("### Which suites run each area\n")
    out.append(
        "A different count: each cell is the share of the area's lines that suite runs at all, so a line "
        "run by several suites counts in each.\n"
    )
    hb = [(page_title(p).strip("`"), shares(e, BACK_COLS)) for p, e in back.items()]
    out.append(
        charts.picture("code-map-heat-back", "Heatmap: the share of each back-end area's lines each layer runs") + "\n"
    )
    out.append(heat_table(hb, list(BACK_COLS), "Back end") + "\n")
    if front:
        hf = [(a, shares(e, SITE_COLS)) for a, e in front.items()]
        out.append(
            charts.picture("code-map-heat-front", "Heatmap: the share of each front-end area's lines each suite runs")
            + "\n"
        )
        out.append(heat_table(hf, list(SITE_COLS), "Front end") + "\n")
        out += compare_suites(cov, front)
    return out


def compare_suites(cov: Coverage, front: dict) -> list[str]:
    """Where Playwright and Selenium run different code, by folder; the lines are on Code-site."""
    out = ["### Playwright and Selenium compared\n"]
    if not cov.front.get("selenium"):
        return out + ["Not measured in this run: the Selenium suite ran without coverage.\n"]
    out.append(
        "The two browser suites test the same pages. Lines one of them runs and the other doesn't, by "
        f"folder; each file's lines are on [Front end (site)](Code-{SITE}#playwright-and-selenium-compared).\n"
    )
    out += [
        "| Folder | Lines | Playwright runs, Selenium doesn't | Selenium runs, Playwright doesn't |",
        "|---|--:|--:|--:|",
    ]
    for area, files in site_areas(cov.front).items():
        pw = sum(count(e["playwright_only"]) for _, e in files)
        sel = sum(count(e["selenium_only"]) for _, e in files)
        out.append(f"| {area} | {front[area]['lines']:,} | {pw:,} | {sel:,} |")
    return out + [""]


def count(ranges: list[list[int]] | None) -> int:
    """How many lines a list of ranges holds."""
    return sum(b - a + 1 for a, b in ranges or [])


def site_source(repo: str, commit: str, path: str) -> str:
    """A front-end file's source link: an .astro file's script block links to the .astro file."""
    return source_link(repo, commit, "site/" + re.sub(r" \(script \d+\)$", "", path))


def site_ranges(ranges: list[list[int]], repo: str, commit: str, path: str) -> str:
    """Line ranges of a front-end file, linked; an .astro script block's lines are its own, so unlinked."""
    if path.endswith(")"):
        return ", ".join(f"{a}" if a == b else f"{a}–{b}" for a, b in ranges)
    return line_ranges(ranges, repo, commit, "site/" + path)


def page_site(cov: Coverage, repo: str, commit: str) -> str:
    """The front end's page: a chart per folder, then each file's lines and the cases that run it."""
    front = cov.front
    areas = site_areas(front)
    out = [
        "# Front end (site)\n",
        "> Generated, do not edit. Made from the code map on every update of the wiki.\n",
        coverage_note(cov, repo, commit),
        "The site's own code (`site/src`: the scripts, the build code in `lib`, the components' and pages' "
        "script blocks), as the front-end coverage badge counts it. Vitest is measured per test file, so a "
        "file's Vitest cases are all the cases of the test files that run it; Playwright per case; "
        "Selenium per test. Statuses as on [the code reference](Code#the-map). An `.astro` file's script "
        "block is numbered as the build numbers it; its line numbers count from the block's start.\n",
        "[Code reference](Code) · "
        + " · ".join(f"[{a}](#{anchor(a)})" for a in areas)
        + " · [Playwright and Selenium compared](#playwright-and-selenium-compared)\n",
    ]
    for area, files in areas.items():
        out.append(f"## {area}\n")
        out.append(
            charts.picture(
                f"code-map-site-{area.replace('/', '-')}", f"Stacked bars: the lines of each file in {area}, by status"
            )
            + "\n"
        )
        out.append(
            status_table(
                [(f"`{f.split('/', 2)[-1] if area == 'lib' else f.rsplit('/', 1)[-1]}`", e) for f, e in files],
                SITE_STATUSES,
                "File",
            )
            + "\n"
        )
        for f, e in files:
            out.append(f"### `{f}`\n")
            out.append(f"[source]({site_source(repo, commit, f)})\n")
            line = f"**Tests:** {e['lines']} lines with code: " + ", ".join(f"{k} {e[k]}" for k in SITE_STATUSES)
            if e["no_test"]:
                line += f" (no test: lines {site_ranges(e['no_test'], repo, cov.commit, f)})"
            out.append(line + ".\n")
            groups = {k: [front["tests"][i] for i in e["tests"].get(k, [])] for k in (*SITE_LAYERS, "selenium")}
            if any(groups.values()):
                summary = ", ".join(f"{NAMES[k]} {len(v)}" for k, v in groups.items() if v)
                out.append(f"<details><summary>Tests that run it: {summary}</summary>\n")
                for k, keys in groups.items():
                    if keys:
                        out.append(f"{NAMES[k]}:\n")
                        out += [f"- {link}" for key in keys for link in cov.front_link(key)]
                        out.append("")
                out.append("</details>\n")
    out.append("## Playwright and Selenium compared\n")
    if not front.get("selenium"):
        out.append("Not measured in this run: the Selenium suite ran without coverage.\n")
    else:
        rows = [(f, e) for fs in areas.values() for f, e in fs if e["playwright_only"] or e["selenium_only"]]
        out.append(
            "Lines one browser suite runs and the other doesn't. Files where both run the same lines are left out.\n"
        )
        out += ["| File | Playwright runs, Selenium doesn't | Selenium runs, Playwright doesn't |", "|---|---|---|"]
        for f, e in sorted(rows):
            pw = (
                f"{count(e['playwright_only'])}: {site_ranges(e['playwright_only'], repo, cov.commit, f)}"
                if e["playwright_only"]
                else ""
            )
            sel = (
                f"{count(e['selenium_only'])}: {site_ranges(e['selenium_only'], repo, cov.commit, f)}"
                if e["selenium_only"]
                else ""
            )
            out.append(f"| `{f}` | {pw} | {sel} |")
        if not rows:
            out.append("| None: both suites run the same lines | | |")
    return "\n".join(out).rstrip() + "\n"


NAMES = {"unit": "Vitest unit", "integration": "Vitest integration", "e2e": "Playwright", "selenium": "Selenium"}


def chart_files(pages: dict[str, list[Module]], cov: Coverage) -> dict[str, str]:
    """Every chart the pages show, light and dark: {file name: SVG}."""
    out: dict[str, str] = {}
    back = {
        page: summed([cov.modules[m.path] for m in mods if m.path in cov.modules], BACK_STATUSES)
        for page, mods in pages.items()
    }
    back = {p: e for p, e in back.items() if e["lines"]}
    rows = [("#", "Back end (Python)")] + [
        (page_title(p).strip("`").removeprefix("traceconomics."), e) for p, e in back.items()
    ]
    areas = site_areas(cov.front) if cov.front else {}
    front = {a: summed([e for _, e in fs], SITE_STATUSES) for a, fs in areas.items()}
    if front:
        rows += [("#", "Front end (site)")] + list(front.items())
    counts = [(lab, {k: e.get(k, 0) for k in charts.STATUS_ORDER} if lab != "#" else e) for lab, e in rows]
    out |= charts.pair(
        "code-map-overview",
        lambda th: charts.bars(counts, "Lines per area, by the first test layer that runs them", th, 150),
    )
    hb = [(page_title(p).strip("`").removeprefix("traceconomics."), shares(e, BACK_COLS)) for p, e in back.items()]
    out |= charts.pair(
        "code-map-heat-back",
        lambda th: charts.heatmap(
            hb, list(BACK_COLS), "Back end: the share of each area's lines each layer runs", th, 150
        ),
    )
    if front:
        hf = [(a, shares(e, SITE_COLS)) for a, e in front.items()]
        out |= charts.pair(
            "code-map-heat-front",
            lambda th: charts.heatmap(
                hf, list(SITE_COLS), "Front end: the share of each folder's lines each suite runs", th, 150
            ),
        )
        for area, files in areas.items():
            fr = [
                (f.rsplit("/", 1)[-1] if area != "lib" else f.split("/", 2)[-1], {k: e[k] for k in SITE_STATUSES})
                for f, e in files
            ]
            out |= charts.pair(
                f"code-map-site-{area.replace('/', '-')}",
                lambda th, fr=fr, area=area: charts.bars(fr, f"Site, {area}: lines per file", th),
            )
    for page, mods in pages.items():
        mr = [
            (module_label(m), {k: cov.modules[m.path][k] for k in BACK_STATUSES})
            for m in mods
            if cov.modules.get(m.path, {}).get("lines")
        ]
        if mr:
            name = page_title(page).strip("`")
            out |= charts.pair(
                f"code-map-{page}", lambda th, mr=mr, name=name: charts.bars(mr, f"{name}: lines per module", th)
            )
    return out


def share(n: int, total: int) -> str:
    """A share as a whole percent, "<1%" for a small one that isn't nothing."""
    return "<1%" if 0 < 100 * n / total < 0.5 else f"{100 * n / total:.0f}%"


def overview_tests(cov: Coverage) -> list[str]:
    """The tests that run no package code: the repository's own checks, then the rest; and runs without a case."""
    out = ["", "## Checks on the code itself\n"]
    out.append(
        "The `repository` layer: tests that check the repository's own files (the docstrings, the wiki "
        "pages, the lock files, the fixtures, the test tooling) and run no package code, so they appear "
        "on no module above. By test file:\n"
    )
    by_file = defaultdict(list)
    for c in cov.catalog:
        if c.get("layer") == "repository":
            by_file[c["file"]].append(c)
    if not by_file:
        out.append("None in the stored catalog.\n")
    for f in sorted(by_file):
        out.append(f"- `{f}`")
        out += [f"  - {cov.case_link(c['node'])}" for c in sorted(by_file[f], key=lambda c: c["id"])]
    ran = set(cov.tests)
    quiet = sorted((c for c in cov.catalog if c.get("layer") in LAYERS and c["node"] not in ran), key=lambda c: c["id"])
    out.append("\n## Unit and integration tests that run no package code\n")
    out.append(
        "They test helpers under `tests/` (the made-up site data, the bibliography's reader), or run the "
        "package in a separate process, which the coverage doesn't follow.\n"
    )
    out += [f"- {cov.case_link(c['node'])} ({c['layer']})" for c in quiet] or ["None."]
    lost = sorted(n for n in cov.tests if n not in cov.cases)
    out.append("\n## Test runs without a case\n")
    out += [f"- `{n}`" for n in lost] or ["None: every test that runs package code has its case."]
    return out


SIDEBAR_NAMES = {TOP: "Top-level modules"}
# The code map's own block, in the sidebar's Testing list (wiki/_Sidebar.md): the map is about tests.
MAP_START, MAP_END = "<!-- codemap:start -->", "<!-- codemap:end -->"


def _replace(text: str, start: str, end: str, block: str) -> str:
    """The text with the block between `start` and `end` replaced, or the block added at the end."""
    if start in text and end in text:
        return re.sub(re.escape(start) + r".*?" + re.escape(end), lambda _: block, text, flags=re.S)
    return (text.rstrip() + "\n\n" if text.strip() else "") + block + "\n"


def sidebar(text: str, pages: list[str], code_map: bool = False) -> str:
    """The sidebar with its two blocks replaced: the code reference, and the code map (when there is one)."""
    block = "\n".join(
        [
            START,
            "- [Code reference](Code)",
            *[f"  - [{SIDEBAR_NAMES.get(p, p)}](Code-{p})" for p in pages if p != SITE],
            "  " + END,
        ]
    )
    text = _replace(text, START, END, block)
    lines = ["- [Code map](Code#the-map)", "  - [Overview](Code#the-map)"]
    if SITE in pages:
        lines.append(f"  - [Front end (site)](Code-{SITE})")
    map_block = "\n".join([MAP_START, *(lines if code_map else []), "  " + MAP_END])
    if not code_map and MAP_START not in text:
        return text  # no map, and nowhere marked for it: nothing to add
    return _replace(text, MAP_START, MAP_END, map_block)


def generate(
    src: Path, out: Path, repo: str, commit: str, root: Path | None = None, store: Path | None = None
) -> list[str]:
    """Write the code pages and the sidebar block into `out`; return the page names written."""
    root = root or src.parent.parent
    pages = packages(src, root)
    cov = Coverage.load(store) if store else None
    found = store / "mutation.json" if store else None
    mutation = json.loads(found.read_text(encoding="utf-8")) if found and found.is_file() else None
    texts = {"Code": page_overview(pages, repo, commit, cov)}
    for page, modules in pages.items():
        texts[f"Code-{page}"] = page_package(page, modules, repo, commit, cov, mutation, root)
    if cov is not None and cov.front is not None:
        texts[f"Code-{SITE}"] = page_site(cov, repo, commit)
    svgs = chart_files(pages, cov) if cov is not None else {}
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("Code-*.md"):
        if old.stem not in texts:
            old.unlink()
    for old in out.glob("code-map-*.svg"):
        if old.name not in svgs:
            old.unlink()
    for name, text in texts.items():
        (out / f"{name}.md").write_text(text, encoding="utf-8", newline="\n")
    for name, text in svgs.items():
        (out / name).write_text(text, encoding="utf-8", newline="\n")
    sb = out / "_Sidebar.md"
    listed = [*pages, *([SITE] if f"Code-{SITE}" in texts else [])]
    sb.write_text(
        sidebar(sb.read_text(encoding="utf-8") if sb.is_file() else "", listed, cov is not None),
        encoding="utf-8",
        newline="\n",
    )
    return sorted(texts)


def main(argv=None):
    """The command line: the source folder, the wiki checkout, the repository and the commit."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--src", required=True, type=Path, help="the package folder, e.g. src/traceconomics")
    ap.add_argument("--out", required=True, type=Path, help="a checkout of the wiki")
    ap.add_argument("--repo", required=True, help="OWNER/NAME, for the source links")
    ap.add_argument("--commit", required=True, help="the commit the source is at")
    ap.add_argument("--store", type=Path, help="the branch test-history, for code-map.json and catalog.json")
    a = ap.parse_args(argv)
    if not re.fullmatch(r"[0-9a-f]{7,40}", a.commit):
        ap.error(f"--commit must be a commit hash, not {a.commit!r}")
    print("wrote " + ", ".join(generate(a.src, a.out, a.repo, a.commit, store=a.store)))


if __name__ == "__main__":
    main()
