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
    r = _Reader()
    r.feed(decode(data) if isinstance(data, bytes) else data)
    r.close()
    return r


def visible_text(data: bytes | str) -> str:
    """The page's visible text, one non-empty line per block, whitespace squashed."""
    lines = (_squash(line) for line in "".join(read(data).text).split("\n"))
    return "\n".join(line for line in lines if line)


def links(data: bytes | str) -> list[tuple[str, str]]:
    """(href, link text) pairs in page order."""
    return read(data).links


def table_rows(data: bytes | str) -> list[list[tuple[str, str]]]:
    """Table rows as lists of (cell class, cell text)."""
    return read(data).rows
