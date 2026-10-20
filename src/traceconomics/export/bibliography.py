"""The bibliography as plain data for the website: every entry's fields, LaTeX markup taken off.

    <out>/v1/references.json   {key: {entrytype, author, title, ...}} for every entry (`entrytype`
                               is BibTeX's @type; a report's own `type` field is kept as `type`)

The site formats a reference from these fields; it never parses BibTeX. Only the markup the
bibliography uses is undone: braces that protect case, \\_ and \\&, and -- for an en dash.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from traceconomics import references
from traceconomics.checks import require

ENTRY = re.compile(r"@(\w+)\s*\{\s*([^,\s]+)\s*,")
FIELD = re.compile(r"\s*(\w+)\s*=\s*")


def _braced(src: str, i: int) -> tuple[str, int]:
    """The text inside the braces opening at src[i], and the index after the closing brace."""
    require(src[i] == "{", f"expected '{{' at {i}")
    depth, j = 0, i
    while j < len(src):
        if src[j] == "{" and src[j - 1] != "\\":
            depth += 1
        elif src[j] == "}" and src[j - 1] != "\\":
            depth -= 1
            if depth == 0:
                return src[i + 1:j], j + 1
        j += 1
    raise ValueError(f"unbalanced braces from {i}")


def plain(value: str) -> str:
    text = value.replace(r"\_", "_").replace(r"\&", "&").replace("---", "—").replace("--", "–")
    text = re.sub(r"(?<!\\)[{}]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def parse(src: str) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for m in ENTRY.finditer(src):
        _, end = _braced(src, src.index("{", m.start()))
        body = src[m.end():end - 1]
        fields: dict[str, str] = {"entrytype": m.group(1).lower()}
        i = 0
        while True:
            f = FIELD.match(body, i)
            if not f:
                break
            j = f.end()
            if body[j] == "{":
                value, j = _braced(body, j)
            else:
                k = body.find(",", j)
                value, j = body[j:k if k >= 0 else len(body)], (k if k >= 0 else len(body))
            fields[f.group(1).lower()] = value if f.group(1).lower() == "url" else plain(value)
            i = body.find(",", j)
            if i < 0:
                break
            i += 1
        out[m.group(2)] = fields
    return out


def export(out: Path) -> Path:
    entries = parse(references.text())
    require(set(entries) == set(references.entries()), "the bibliography parser and the key reader disagree")
    path = Path(out) / "v1" / "references.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"format": "v1", "references": entries}, ensure_ascii=False, indent=1) + "\n",
                    encoding="utf-8")
    return path
