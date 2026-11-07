"""The wiki's hand-written pages (wiki/) stay true to the repository: every file or folder they name
exists, and every link to another wiki page has a page behind it. The cheap guard against an
architecture page that describes code which moved or no longer exists."""

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.repository

ROOT = Path(__file__).resolve().parent.parent
WIKI = ROOT / "wiki"
PAGES = sorted(WIKI.glob("*.md"))
# Pages wiki.py writes on every run; they exist only in the wiki itself.
GENERATED = re.compile(r"^Tests(-[A-Za-z]+)?$")
# Where a short path in the text may start: the root, the package, its sources, the site.
BASES = [ROOT, ROOT / "src/traceconomics", ROOT / "src/traceconomics/sources", ROOT / "site"]
EXTENSIONS = (".py", ".toml", ".md", ".ts", ".mjs", ".bib", ".json", ".yml", ".cff")
SKIP_DIRS = {"node_modules", ".venv", ".git", "dist", "coverage"}


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
    if "/" not in path:            # a bare file name: somewhere in the repository
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
    Then each one has a page in wiki/, or is one of the generated Tests pages
    """
    links = re.findall(r"\]\(([^)\s#]+)(?:#[^)]*)?\)", page.read_text(encoding="utf-8"))
    local = [x for x in links if not re.match(r"^[a-z]+:|^/|\.", x) and "/" not in x]
    missing = [x for x in local if not (WIKI / f"{x}.md").is_file() and not GENERATED.match(x)]
    assert missing == [], f"{page.name} links to wiki pages that don't exist: {missing}"
