"""The wiki's hand-written pages (wiki/) stay true to the repository: every file or folder they name
exists, every link to another wiki page has a page behind it, and every block they quote from the
code still says what the code's docstring says. The cheap check against an architecture or method
page that describes code which moved, no longer exists, or has changed."""

import ast
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / "catalog"))
from cases import renamed  # noqa: E402
from rules_page import declared_ids  # noqa: E402

pytestmark = pytest.mark.repository

ROOT = Path(__file__).resolve().parent.parent
WIKI = ROOT / "wiki"
PAGES = sorted(WIKI.glob("*.md"))
# Pages wiki.py, code_reference.py, code_map_pages.py, checks_page.py, rules_page.py and tests/evals/page.py write on
# every run; they exist only in the wiki itself.
GENERATED = re.compile(r"^((Tests|Code)(-[A-Za-z0-9-]+)?|Checks|Rules-guides-and-sensors|Agent-evals)$")
# Where a short path in the text may start: the root, the package, its sources, the site.
BASES = [ROOT, ROOT / "src/traceconomics", ROOT / "src/traceconomics/sources", ROOT / "site"]
EXTENSIONS = (".py", ".toml", ".md", ".ts", ".mjs", ".bib", ".json", ".yml", ".cff")
SKIP_DIRS = {"node_modules", ".venv", ".git", "dist", "coverage"}
# A block quoted from the code: `<!-- from: traceconomics.engine.chain -->`, then a fenced block.
QUOTED = re.compile(r"<!-- from: ([\w.]+) -->\s*```[a-z]*\n(.*?)\n```", re.S)
FENCE = re.compile(r"^```[a-z]*\n(.*?)\n```", re.S | re.M)
# On these pages every code block is quoted from a docstring, so each one must name its module.
METHOD_PAGES = ["Price-index-methods.md", "Household-group-methods.md"]


def names(page: Path) -> list[str]:
    """Backticked file and folder names: with a slash, or a known extension; no placeholders."""
    out = []
    for token in re.findall(r"`([^`\s]+)`", page.read_text(encoding="utf-8")):
        if any(ch in token for ch in "<>{}*()#@"):
            continue
        if "/" in token.strip("/") or token.endswith("/") or token.endswith(EXTENSIONS):
            out.append(token)
    return out


def exists(token: str) -> bool:
    path = token.rstrip("/")
    if "/" not in path:  # a bare file name: somewhere in the repository
        return any(not SKIP_DIRS & set(p.parts) for p in ROOT.rglob(path))
    return any((base / path).exists() for base in BASES)


def test_there_are_pages():
    """PY-WIKI-001: the wiki has its home page and sidebar

    Given the hand-written wiki pages in wiki/
    When their names are listed
    Then they include Home and _Sidebar
    """
    assert {p.stem for p in PAGES} >= {"Home", "_Sidebar"}


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_named_paths_exist(page):
    """PY-WIKI-002: every path a wiki page names exists in the repository

    Given a hand-written wiki page
    When the backticked file and folder names in it are collected (with a slash or a known extension, no placeholders)
    Then each one exists: a bare file name anywhere in the repository outside skipped folders, a path under the root, the package, its sources or the site
    """
    missing = [t for t in names(page) if not exists(t)]
    assert missing == [], f"{page.name} names paths that don't exist: {missing}"


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_wiki_links_have_a_page(page):
    """PY-WIKI-003: every link to another wiki page has a page behind it

    Given a hand-written wiki page
    When its links to other wiki pages are collected (not URLs, absolute paths, relative files or anchors)
    Then each one has a page in wiki/, or is one of the generated Tests or Code pages
    """
    links = re.findall(r"\]\(([^)\s#]+)(?:#[^)]*)?\)", page.read_text(encoding="utf-8"))
    local = [x for x in links if not re.match(r"^[a-z]+:|^/|\.", x) and "/" not in x]
    missing = [x for x in local if not (WIKI / f"{x}.md").is_file() and not GENERATED.match(x)]
    assert missing == [], f"{page.name} links to wiki pages that don't exist: {missing}"


def module_docstring(dotted: str) -> str | None:
    """The docstring of a module of the package, read from its source; None if there is no such module."""
    rel = Path(*dotted.split("."))
    for path in (ROOT / "src" / rel.with_suffix(".py"), ROOT / "src" / rel / "__init__.py"):
        if path.is_file():
            return ast.get_docstring(ast.parse(path.read_text(encoding="utf-8"))) or ""
    return None


def words(text: str) -> str:
    return " ".join(text.split())


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_quoted_blocks_match_their_docstring(page):
    """PY-WIKI-004: every block a wiki page quotes from the code still matches that module's docstring

    Given a hand-written wiki page with blocks marked `<!-- from: <module> -->`
    When each block is compared with the named module's docstring, whitespace ignored
    Then the module exists
    And its docstring contains the block word for word
    """
    wrong = []
    for module, block in QUOTED.findall(page.read_text(encoding="utf-8")):
        doc = module_docstring(module)
        if doc is None:
            wrong.append(f"{module}: no such module")
        elif words(block) not in words(doc):
            wrong.append(f"{module}: the docstring no longer says:\n{block}")
    assert wrong == [], f"{page.name}:\n" + "\n".join(wrong)


@pytest.mark.parametrize("page", METHOD_PAGES)
def test_every_block_on_a_method_page_names_its_source(page):
    """PY-WIKI-005: every code block on a method page is marked with the module it quotes

    Given the price index and household group method pages
    When their fenced code blocks are listed
    Then the page has at least one
    And each one carries a `<!-- from: <module> -->` marker, so PY-WIKI-004 checks it against the code
    """
    text = (WIKI / page).read_text(encoding="utf-8")
    blocks = FENCE.findall(text)
    quoted = [block for _, block in QUOTED.findall(text)]
    assert blocks, f"{page} has no code block: is this list out of date?"
    unmarked = [b for b in blocks if b not in quoted]
    assert unmarked == [], f"{page}: code blocks without a `<!-- from: <module> -->` marker:\n" + "\n---\n".join(
        unmarked
    )


# A test case ID on a page, and a range of them written out in full: "PY-ENG-008 to PY-ENG-010".
CASE_ID = re.compile(r"\b((?:PY|PW|VT|SEL)-[A-Z0-9]+-)(\d{3})\b")
CASE_RANGE = re.compile(r"\b((?:PY|PW|VT|SEL)-[A-Z0-9]+-)(\d{3}) to \1(\d{3})\b")
# The short form, which no test can check: "PY-ENG-008 to 010", "PY-CALIB-003 and 004".
SHORT_RANGE = re.compile(r"\b(?:PY|PW|VT|SEL)-[A-Z0-9]+-\d{3}\s+(?:to|and)\s+\d{3}\b")
DECLARED = declared_ids(ROOT)
RENAMED = renamed()


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_every_test_id_a_page_names_exists(page):
    """PY-WIKI-006: every test case ID a hand-written page names exists, a range of them included

    Given a hand-written wiki page
    When the test case IDs it names are read, each range "A to B" as every ID from A to B
    Then each one is declared by a test in the repository, and none is an ID renamed away
    And no range is written in the short form ("PY-ENG-008 to 010"), which can't be checked
    """
    text = page.read_text(encoding="utf-8")
    named = {prefix + n for prefix, n in CASE_ID.findall(text)}
    for prefix, a, b in CASE_RANGE.findall(text):
        named |= {f"{prefix}{n:03d}" for n in range(int(a), int(b) + 1)}
    wrong = [f"{i}: renamed to {RENAMED[i]}" for i in sorted(named) if i in RENAMED]
    wrong += [f"{i}: no test declares it" for i in sorted(named) if i not in RENAMED and i not in DECLARED]
    wrong += [f"{m}: write the second ID in full" for m in SHORT_RANGE.findall(text)]
    assert wrong == [], f"{page.name}:\n" + "\n".join(wrong)
