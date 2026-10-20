"""The bibliography: every source the published numbers and their method rely on.

`references.bib` is BibTeX (biblatex style, UTF-8). The build checks that
every cited key exists here; reading the keys needs no BibTeX library.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import cache
from importlib import resources

ENTRY = re.compile(r"^@(\w+)\s*\{\s*([^,\s]+)\s*,", re.MULTILINE)
FIELD = re.compile(r"^\s*(\w+)\s*=\s*\{", re.MULTILINE)


@dataclass(frozen=True)
class Entry:
    type: str
    key: str
    fields: frozenset[str]


def text() -> str:
    return resources.files("traceconomics.references").joinpath("references.bib").read_text(encoding="utf-8")


@cache
def entries() -> dict[str, Entry]:
    """Key -> entry. Raises ValueError on a duplicate key."""
    src = text()
    starts = list(ENTRY.finditer(src))
    out: dict[str, Entry] = {}
    for i, m in enumerate(starts):
        body = src[m.end(): starts[i + 1].start() if i + 1 < len(starts) else len(src)]
        key = m.group(2)
        if key in out:
            raise ValueError(f"duplicate bibliography key {key!r}")
        out[key] = Entry(m.group(1).lower(), key, frozenset(f.lower() for f in FIELD.findall(body)))
    return out


def missing(cited) -> list[str]:
    """The cited keys that aren't in the bibliography, sorted."""
    known = entries()
    return sorted({k for k in cited if k not in known})
