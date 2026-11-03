"""Every page the sitemap lists, and its Greek twin, loads in Chrome with no console error. Every
internal link and data-file link on them answers 200, and a link to `#somewhere` finds that id on
its page. The canonical and alternate links point to built pages.

The links are followed over plain HTTP (one request per address), not by clicking: clicking a few
thousand links would test Chrome, not the site.
"""

import urllib.error
import urllib.request
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

import pytest

from helpers import sitemap_paths

PAGES = sitemap_paths() + [p.replace("/en/", "/el/", 1) for p in sitemap_paths() if p.startswith("/en/")]


class _Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links: list[str] = []
        self.heads: list[tuple[str, str]] = []   # (rel, href) of <link rel=canonical|alternate>
        self.ids: set[str] = set()

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if a.get("id"):
            self.ids.add(a["id"])
        if tag == "a" and a.get("href"):
            self.links.append(a["href"])
        if tag == "link" and a.get("rel") in ("canonical", "alternate") and a.get("href"):
            self.heads.append((a["rel"], a["href"]))


def _get(url: str) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            body = r.read()
            kind = r.headers.get_content_type()
            return r.status, body.decode("utf-8") if kind == "text/html" else ""
    except urllib.error.HTTPError as e:
        return e.code, ""


@pytest.fixture(scope="module")
def crawl(base_url):
    """Each listed page parsed once: its links, head links and ids."""
    pages = {}
    for path in PAGES:
        status, html = _get(base_url + path)
        assert status == 200, f"{path}: {status}"
        p = _Links()
        p.feed(html)
        pages[path] = p
    return pages


@pytest.mark.parametrize("path", PAGES)
def test_page_has_no_console_error(site, path):
    site.open(path)
    assert site.find("main#content")


def test_sitemap_lists_only_offered_languages():
    assert PAGES, "the sitemap lists no page"
    assert all(p.startswith("/en/") for p in sitemap_paths()), "the sitemap lists a language that isn't offered"


def test_internal_links_answer(base_url, crawl):
    targets: dict[str, set[str]] = {}       # address without its #part -> the pages linking to it
    anchors: dict[tuple[str, str], str] = {}
    for page, p in crawl.items():
        for href in p.links:
            url = urlsplit(urljoin(base_url + page, href))
            if f"{url.scheme}://{url.netloc}" != base_url:
                continue                     # another site: not checked here (no network in tests)
            targets.setdefault(url.path, set()).add(page)
            if url.fragment:
                anchors[(url.path, url.fragment)] = page
    broken = []
    ids: dict[str, set[str]] = {}
    for path, pages in sorted(targets.items()):
        status, html = _get(base_url + path)
        if status != 200:
            broken.append(f"{path} ({status}), linked from {sorted(pages)[0]}")
        elif html:
            p = _Links()
            p.feed(html)
            ids[path] = p.ids
    for (path, fragment), page in sorted(anchors.items()):
        if path in ids and fragment not in ids[path]:
            broken.append(f"{path}#{fragment}: no such id, linked from {page}")
    assert not broken, "\n".join(broken)
    assert any("/data/v1/" in p for p in targets), "no data file link was checked"


def test_canonical_and_alternates_point_to_built_pages(base_url, crawl):
    wrong = []
    for page, p in crawl.items():
        canonical = [h for rel, h in p.heads if rel == "canonical"]
        if len(canonical) != 1:
            wrong.append(f"{page}: {len(canonical)} canonical links")
            continue
        if urlsplit(canonical[0]).path != page:
            wrong.append(f"{page}: canonical is {canonical[0]}")
        for rel, href in p.heads:
            status, _ = _get(base_url + urlsplit(href).path)
            if status != 200:
                wrong.append(f"{page}: {rel} {href} answers {status}")
    assert not wrong, "\n".join(wrong)
