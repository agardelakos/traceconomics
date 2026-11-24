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

Standard library only. The same source and commit give the same bytes.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

HEAD = (
    "> Generated, do not edit. Made from the code's docstrings on every update of the wiki; a correction "
    "goes into the docstring, and this page follows.\n"
)
START, END = "<!-- code:start -->", "<!-- code:end -->"
TOP = "top-level"  # the page name of the modules directly in the package
INDENT = 4  # docstring lines indented this much are code (formulas, layouts); lists nest by 2
LAYERS = ("unit", "integration")  # the layers that run package code, the lowest first
TESTS_PAGE = "Tests-pytest"


@dataclass
class Coverage:
    """What the tests run, from the stored code map, with each test joined to its case."""

    commit: str
    modules: dict  # path -> the map's entry (tests/coverage/code_map.py)
    tests: list[str]  # node IDs; the map's entries refer to them by position
    cases: dict  # node ID -> the catalog's pytest case
    catalog: list[dict]  # every pytest case

    @staticmethod
    def load(store: Path) -> Coverage | None:
        """The map and catalog stored in `store`, or None when there is no map yet."""
        if not (store / "code-map.json").is_file():
            return None
        m = json.loads((store / "code-map.json").read_text(encoding="utf-8"))
        cat = store / "catalog.json"
        cases = json.loads(cat.read_text(encoding="utf-8"))["cases"] if cat.is_file() else []
        pytest_cases = [c for c in cases if c["suite"] == "pytest" and c.get("id")]
        back = m["back-end"]
        return Coverage(m["commit"], back["modules"], back["tests"], {c["node"]: c for c in pytest_cases}, pytest_cases)

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


def page_package(page: str, modules: list[Module], repo: str, commit: str, cov: Coverage | None = None) -> str:
    """One package's page: each module's docstring and its public members, linked to their source lines."""
    out = [
        f"# {page_title(page)}\n",
        HEAD,
        f"Made from commit [`{commit[:7]}`]({commit_link(repo, commit)}).\n",
    ]
    if cov is not None:
        out.append(coverage_note(cov, repo, commit))
    out.append("[Code reference](Code) · " + " · ".join(f"[`{m.name}`](#{anchor(m.name)})" for m in modules) + "\n")
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
        out += overview_tests(cov)
    return "\n".join(out) + "\n"


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


def sidebar(text: str, pages: list[str]) -> str:
    """The sidebar with its code block replaced, or added at the end when it has no markers yet."""
    block = "\n".join(
        [
            START,
            "- [Code reference](Code)",
            *[f"  - [{'Top-level modules' if p == TOP else p}](Code-{p})" for p in pages],
            "  " + END,
        ]
    )
    if START in text and END in text:
        return re.sub(re.escape(START) + r".*?" + re.escape(END), lambda _: block, text, flags=re.S)
    return (text.rstrip() + "\n\n" if text.strip() else "") + block + "\n"


def generate(
    src: Path, out: Path, repo: str, commit: str, root: Path | None = None, store: Path | None = None
) -> list[str]:
    """Write the code pages and the sidebar block into `out`; return the page names written."""
    root = root or src.parent.parent
    pages = packages(src, root)
    cov = Coverage.load(store) if store else None
    texts = {"Code": page_overview(pages, repo, commit, cov)}
    for page, modules in pages.items():
        texts[f"Code-{page}"] = page_package(page, modules, repo, commit, cov)
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("Code-*.md"):
        if old.stem not in texts:
            old.unlink()
    for name, text in texts.items():
        (out / f"{name}.md").write_text(text, encoding="utf-8", newline="\n")
    sb = out / "_Sidebar.md"
    sb.write_text(
        sidebar(sb.read_text(encoding="utf-8") if sb.is_file() else "", list(pages)), encoding="utf-8", newline="\n"
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
