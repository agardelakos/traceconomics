"""Test cases as data: one Case per stable ID, read from the tests themselves.

A case is written on the test that implements it, so it can't drift from the code:

- pytest and Selenium (Python): the test's docstring.

      PY-ENG-012: chain-linking carries December over

      Given an index with a December link month
      When the next year is chain-linked
      Then the December value carries over unchanged

      Optional notes after a blank line: the reason for the rule, kept with the case.

  `And` and `But` continue the step above them. A test that acts more than once lists every action
  under When and every check under Then, each check saying which action it follows ("And after the
  reset, …"); "And when …" is refused. A parametrized test is one Scenario Outline: one ID, its
  parameter sets are the examples.

- Playwright: the test's annotations, `{ type: "id" | "title" | "given" | "when" | "then",
  description }`; a repeated type continues the step above it. The title is optional: without
  it the case takes the test's title (an outline, the part its examples' titles share).
- Vitest: the test option `meta: { id, title?, given, when, then }`, each step a string or a list.

One ID may sit on several tests only within one file, as examples of one outline (a parametrize,
a loop over languages, `test.each`), and they must carry the same steps. An ID is never reused:
once its test is gone it is obsolete for good.

Defect links: an `xfail`, `skip` or `fixme` reason that names `#<issue>` links the case to it.

Standard library only.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

SUITES = {"pytest": "PY", "selenium": "SEL", "playwright": "PW", "vitest": "VT"}
ID = re.compile(r"^(PY|SEL|PW|VT)-([A-Z][A-Z0-9]{1,9})-(\d{3})$")
HEADER = re.compile(r"^\s*([A-Z]+-[A-Z0-9]+-\d+)\s*:\s*(.+?)\s*$")
STEP = re.compile(r"^(Given|When|Then|And|But)\b\s*(.*)$")
ISSUE = re.compile(r"(?<![\w/])#(\d+)\b")


@dataclass
class Case:
    """One test case: what the catalog, the validator, the run history and the wiki share."""

    id: str | None  # None: a test with no case yet
    suite: str  # pytest | selenium | playwright | vitest
    title: str
    file: str  # repository-relative path
    line: int
    node: str  # the test's own name in its suite (pytest node ID without
    # parameters; Playwright and Vitest: file › titles)
    given: list[str] = field(default_factory=list)
    when: list[str] = field(default_factory=list)
    then: list[str] = field(default_factory=list)
    notes: str = ""
    examples: list[str] = field(default_factory=list)  # outline examples (parameter IDs, titles)
    defects: list[int] = field(default_factory=list)  # issue numbers
    tags: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)  # what the reader found wrong in the text
    named: bool = False  # the title was given with the case, not taken from the test

    def to_json(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_json(d: dict) -> Case:
        return Case(**d)


def area(case_id: str) -> str | None:
    m = ID.match(case_id or "")
    return m.group(2) if m else None


def issues(text: str | None) -> list[int]:
    return sorted({int(n) for n in ISSUE.findall(text or "")})


def _steps(lines: list[str]) -> tuple[dict[str, list[str]], list[str]]:
    """Given/When/Then lines into three lists; And/But continue the previous keyword."""
    steps = {"given": [], "when": [], "then": []}
    problems: list[str] = []
    current = None
    order = {"given": 0, "when": 1, "then": 2}
    for raw in lines:
        m = STEP.match(raw.strip())
        if not m:
            problems.append(f"not a Given/When/Then line: {raw.strip()!r}")
            continue
        word, text = m.group(1).lower(), m.group(2).strip()
        if word in ("and", "but"):
            if current is None:
                problems.append(f"{m.group(1)} before any Given/When/Then")
                continue
            if re.match(r"(when|given)\b", text, re.I):
                # "And when …" files an action under Then: list every action under When instead,
                # and let each Then line say which one it follows.
                problems.append(f"'{m.group(1)} {text.split()[0]} …' hides a step: list every action under When")
            word = current
        elif current is not None and order[word] < order[current]:
            problems.append(f"{m.group(1)} after {current.capitalize()}: steps go Given, When, Then")
        if not text:
            problems.append(f"empty {m.group(1)} step")
            continue
        steps[word].append(text)
        current = word
    return steps, problems


def missing_steps(c: Case) -> list[str]:
    return [k.capitalize() for k in ("given", "when", "then") if not getattr(c, k)]


def from_docstring(doc: str | None) -> dict:
    """A Python test's docstring → id, title, steps, notes, problems. Never raises."""
    out = {"id": None, "title": "", "given": [], "when": [], "then": [], "notes": "", "problems": []}
    if not doc or not doc.strip():
        out["problems"].append("no docstring")
        return out
    lines = [line.rstrip() for line in doc.strip("\n").splitlines()]
    # Dedent like inspect.cleandoc, but keep it simple: the first line is flush already.
    body = lines[1:]
    indent = min((len(x) - len(x.lstrip()) for x in body if x.strip()), default=0)
    lines = [lines[0].strip()] + [x[indent:] for x in body]
    m = HEADER.match(lines[0])
    if not m:
        out["title"] = lines[0].strip()
        out["problems"].append("first line is not 'ID: title'")
        return out
    out["id"], out["title"] = m.group(1), m.group(2)
    rest = lines[1:]
    while rest and not rest[0].strip():
        rest.pop(0)
    block = []
    while rest and rest[0].strip():
        block.append(rest.pop(0))
    steps, problems = _steps(block)
    out.update(steps)
    out["problems"] += problems
    out["notes"] = "\n".join(rest).strip()
    return out


def from_annotations(annotations: list[dict]) -> dict:
    """Playwright annotations → id, steps, defects, problems."""
    out = {"id": None, "title": None, "given": [], "when": [], "then": [], "defects": [], "problems": []}
    current = None
    for a in annotations or []:
        kind, text = (a.get("type") or "").lower(), (a.get("description") or "").strip()
        if kind == "title":
            out["title"] = text or None
        elif kind == "id":
            if out["id"] and out["id"] != text:
                out["problems"].append(f"two IDs: {out['id']} and {text}")
            out["id"] = text
        elif kind in ("given", "when", "then"):
            if text:
                out[kind].append(text)
            current = kind
        elif kind in ("and", "but"):
            if current and text:
                out[current].append(text)
            else:
                out["problems"].append(f"{kind} before any given/when/then")
        elif kind in ("fail", "fixme", "skip", "issue"):
            out["defects"] += issues(text)
    out["defects"] = sorted(set(out["defects"]))
    return out


def from_meta(meta: dict | None) -> dict:
    """Vitest `meta` → id, steps, problems."""
    out = {"id": None, "title": None, "given": [], "when": [], "then": [], "problems": []}
    meta = meta or {}
    out["id"] = meta.get("id")
    out["title"] = meta.get("title") or None
    for k in ("given", "when", "then"):
        v = meta.get(k)
        out[k] = [v] if isinstance(v, str) else [str(x) for x in (v or [])]
        out[k] = [x.strip() for x in out[k] if x and x.strip()]
    return out
