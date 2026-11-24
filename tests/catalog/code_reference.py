"""The wiki's code reference, generated from the package's docstrings. Never edited by hand.

    python -I tests/catalog/code_reference.py --src src/traceconomics --out WIKI_DIR --repo OWNER/NAME --commit SHA

Reads the package with `ast` (nothing is imported or run) and writes:

    Code.md               the overview: every package, what it is for, its modules
    Code-<package>.md     one page per package: each module's docstring, then its public functions,
                          classes and methods with their first lines, each linked to its source line
    _Sidebar.md           only the block between `<!-- code:start -->` and `<!-- code:end -->`

and removes any other `Code-*.md` it wrote before. Every page starts with "Generated, do not edit"
and names the commit it was made from; the source links point at that commit, so they stay right
when the code moves on. Public means what tests/test_docstrings.py checks: no leading underscore.
The top-level modules (`cli.py`, `job.py`, ...) are one page, `Code-top-level`.

Standard library only. The same source and commit give the same bytes.
"""

from __future__ import annotations

import argparse
import ast
import re
from dataclasses import dataclass, field
from pathlib import Path

HEAD = (
    "> Generated, do not edit. Made from the code's docstrings on every update of the wiki; a correction "
    "goes into the docstring, and this page follows.\n"
)
START, END = "<!-- code:start -->", "<!-- code:end -->"
TOP = "top-level"  # the page name of the modules directly in the package
INDENT = 4  # docstring lines indented this much are code (formulas, layouts); lists nest by 2


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


def page_package(page: str, modules: list[Module], repo: str, commit: str) -> str:
    """One package's page: each module's docstring and its public members, linked to their source lines."""
    out = [
        f"# {page_title(page)}\n",
        HEAD,
        f"Made from commit [`{commit[:7]}`]({commit_link(repo, commit)}).\n",
    ]
    out.append("[Code reference](Code) · " + " · ".join(f"[`{m.name}`](#{anchor(m.name)})" for m in modules) + "\n")
    for m in modules:
        out.append(f"## `{m.name}`\n")
        out.append(f"[{m.path}]({source_link(repo, commit, m.path)})\n")
        if m.doc:
            out.append(render(m.doc) + "\n")
        for mem in m.members:
            label = f"`{mem.name}{mem.signature}`" if mem.kind == "function" else f"class `{mem.name}`"
            out.append(
                f"- {label} ([source]({source_link(repo, commit, m.path, mem.line)})): {inline(first_line(mem.doc))}"
            )
            for meth in mem.members:
                out.append(
                    f"  - `{meth.name}{meth.signature}` ([source]({source_link(repo, commit, m.path, meth.line)})): "
                    f"{inline(first_line(meth.doc))}"
                )
        if m.members:
            out.append("")
    return "\n".join(out).rstrip() + "\n"


def page_overview(pages: dict[str, list[Module]], repo: str, commit: str) -> str:
    """The overview: one row per package, with what it is for and how many modules and public members it has."""
    out = [
        "# Code reference\n",
        HEAD,
        f"Made from commit [`{commit[:7]}`]({commit_link(repo, commit)}). Every module of the "
        "`traceconomics` package, with what its docstrings say. A page per package lists each module's "
        "docstring and its public functions and classes, each linked to its source line at that commit. "
        "Only what has no leading underscore is listed; the tests require a docstring on all of it.\n",
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
        out.append(f"| [{page_title(page)}](Code-{page}) | {inline(about)} | {len(modules)} | {count} |")
    return "\n".join(out) + "\n"


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


def generate(src: Path, out: Path, repo: str, commit: str, root: Path | None = None) -> list[str]:
    """Write the code pages and the sidebar block into `out`; return the page names written."""
    root = root or src.parent.parent
    pages = packages(src, root)
    texts = {"Code": page_overview(pages, repo, commit)}
    for page, modules in pages.items():
        texts[f"Code-{page}"] = page_package(page, modules, repo, commit)
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
    a = ap.parse_args(argv)
    if not re.fullmatch(r"[0-9a-f]{7,40}", a.commit):
        ap.error(f"--commit must be a commit hash, not {a.commit!r}")
    print("wrote " + ", ".join(generate(a.src, a.out, a.repo, a.commit)))


if __name__ == "__main__":
    main()
