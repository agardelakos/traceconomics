"""Small HTML readers built on the standard library.

Web pages change on every request (session IDs, scripts, timestamps), so
change detection works on what a reader sees: the visible text, or the list
of links. Tables are read as rows of cell text.
"""

from __future__ import annotations

import html
from html.parser import HTMLParser

SKIP = {"script", "style", "noscript", "template", "head"}


def decode(data: bytes) -> str:
    """The bytes as text: UTF-8, else the Greek Windows code page with undecodable bytes replaced."""
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("cp1253", "replace")  # Greek Windows code page


class _Reader(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip = 0
        self.text: list[str] = []
        self.links: list[tuple[str, str]] = []
        self.rows: list[list[tuple[str, str]]] = []  # cells as (class, text)
        self._href: str | None = None
        self._link_text: list[str] = []
        self._cell: list[str] | None = None
        self._cell_class = ""
        self._row: list[tuple[str, str]] | None = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in SKIP:
            self.skip += 1
        elif tag == "a" and a.get("href"):
            self._href, self._link_text = a["href"], []
        elif tag == "tr":
            self._row = []
        elif tag in ("td", "th"):
            self._cell, self._cell_class = [], a.get("class") or ""
        elif tag in ("br", "p", "div", "li"):
            self.text.append("\n")

    def handle_endtag(self, tag):
        if tag in SKIP:
            self.skip = max(0, self.skip - 1)
        elif tag == "a" and self._href is not None:
            self.links.append((html.unescape(self._href), _squash(" ".join(self._link_text))))
            self._href = None
        elif tag in ("td", "th") and self._cell is not None:
            if self._row is not None:
                self._row.append((self._cell_class, _squash(" ".join(self._cell))))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            self.rows.append(self._row)
            self._row = None

    def handle_data(self, data):
        if self.skip:
            return
        self.text.append(data)
        if self._href is not None:
            self._link_text.append(data)
        if self._cell is not None:
            self._cell.append(data)


def _squash(s: str) -> str:
    return " ".join(s.split())


def read(data: bytes | str) -> _Reader:
    """Parse a page once; the reader holds its visible text pieces, its links and its table rows."""
    r = _Reader()
    r.feed(decode(data) if isinstance(data, bytes) else data)
    r.close()
    return r


def visible_text(data: bytes | str) -> str:
    """The page's visible text, one non-empty line per block, whitespace squashed."""
    lines = (_squash(line) for line in "".join(read(data).text).split("\n"))
    return "\n".join(line for line in lines if line)


VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}


class _Blocks(HTMLParser):
    """Collects the markup inside every element carrying one class, as plain text and links."""

    def __init__(self, cls: str):
        super().__init__(convert_charrefs=True)
        self.cls = cls
        self.found = 0
        self.open: list[str] = []  # tags open inside the current block; empty when outside one
        self.skip = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if not self.open:
            if tag not in VOID and self.cls in (a.get("class") or "").split():
                self.found += 1
                self.open.append(tag)
                self.parts.append("\n")
            return
        # A link's target is part of the terms: a new address for a policy document
        # is a change to read, even when the visible words stay the same.
        target = a.get("href") if tag == "a" else a.get("src") if tag in ("iframe", "embed") else None
        if target:
            self.parts.append(f"\n[{tag}: {html.unescape(target)}]\n")
        if tag in SKIP:
            self.skip += 1
        if tag in ("br", "p", "div", "li", "h1", "h2", "h3", "h4", "tr"):
            self.parts.append("\n")
        if tag not in VOID:
            self.open.append(tag)

    def handle_endtag(self, tag):
        # Pages leave elements unclosed (<p>, <li>), so an end tag closes everything opened
        # after its start tag, as browsers do; a stray end tag is ignored.
        if tag not in self.open:
            return
        while self.open:
            closed = self.open.pop()
            if closed in SKIP:
                self.skip = max(0, self.skip - 1)
            if closed == tag:
                break
        self.parts.append("\n")

    def handle_data(self, data):
        if self.open and not self.skip:
            self.parts.append(data)


def block_text(data: bytes | str, cls: str) -> str | None:
    """The visible text and link targets inside every element with the class ``cls``, in page order.

    None if no such element exists: the page's layout has changed, and the caller must not
    fall back to another part of the page.
    """
    r = _Blocks(cls)
    r.feed(decode(data) if isinstance(data, bytes) else data)
    r.close()
    if not r.found:
        return None
    lines = (_squash(line) for line in "".join(r.parts).split("\n"))
    return "\n".join(line for line in lines if line)


def links(data: bytes | str) -> list[tuple[str, str]]:
    """(href, link text) pairs in page order."""
    return read(data).links


def table_rows(data: bytes | str) -> list[list[tuple[str, str]]]:
    """Table rows as lists of (cell class, cell text)."""
    return read(data).rows
