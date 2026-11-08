"""One check's result: every period compared, how often the two sides agree, and why they differ."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from importlib import resources

from traceconomics.checks import require

# Why two published figures differ. Only "rounding" is found by the code itself; the others come
# from the explanations file, each with its evidence. "not-known" is the honest default.
CATEGORIES = ("rounding", "revision", "rebasing", "splice", "definition", "not-known")


@dataclass(frozen=True)
class Explanation:
    check: str
    periods: tuple[str, ...]
    category: str
    evidence: str        # a key in references.bib
    finding: str         # the site's page for it, a slug


@dataclass(frozen=True)
class Comparison:
    period: str
    published: float
    rebuilt: float
    agree: bool
    explanation: str = ""   # a CATEGORIES value when they don't agree
    finding: str = ""

    @property
    def difference(self) -> float:
        return self.rebuilt - self.published


@dataclass
class Check:
    id: str                  # stable: it names the files and the site's pages
    country: str             # ISO 3166-1 alpha-2, lower case
    unit: str
    tolerance: float         # the largest difference, in `unit`, still counted as agreement
    published: dict          # {"source", "reference", "label"}
    rebuilt: dict            # the same, for the side we compute or the second source
    comparisons: list[Comparison] = field(default_factory=list)
    extra: dict = field(default_factory=dict)   # check-specific figures, e.g. agreement by year

    @property
    def agree(self) -> int:
        return sum(c.agree for c in self.comparisons)

    def summary(self) -> dict:
        by: dict[str, int] = {}
        for c in self.comparisons:
            if not c.agree:
                by[c.explanation] = by.get(c.explanation, 0) + 1
        periods = [c.period for c in self.comparisons]
        # Each year's count compared and agreeing, so a page can show what was checked, not only
        # what differs ("1960-2000: every month agrees").
        years: dict[str, dict[str, int]] = {}
        for c in self.comparisons:
            y = years.setdefault(c.period[:4], {"compared": 0, "agree": 0})
            y["compared"] += 1
            y["agree"] += c.agree
        return {
            "id": self.id, "country": self.country, "unit": self.unit, "tolerance": self.tolerance,
            "published": self.published, "rebuilt": self.rebuilt,
            "first": min(periods) if periods else None, "last": max(periods) if periods else None,
            "compared": len(self.comparisons), "agree": self.agree,
            "by_year": dict(sorted(years.items())),
            "differ": {k: by[k] for k in CATEGORIES if k in by},
            "differences": [{"period": c.period, "published": c.published, "rebuilt": c.rebuilt,
                             "difference": c.difference, "explanation": c.explanation, "finding": c.finding}
                            for c in self.comparisons if not c.agree],
            **({"extra": self.extra} if self.extra else {}),
        }


def load_explanations(text: str | None = None) -> list[Explanation]:
    """The hand-written explanations; refused if one names an unknown category or has no evidence."""
    if text is None:
        text = resources.files("traceconomics.data").joinpath("m5_explanations.toml").read_text(encoding="utf-8")
    out = []
    for e in tomllib.loads(text).get("explanation", []):
        require(e.get("category") in CATEGORIES and e["category"] not in ("rounding", "not-known"),
                f"explanation for {e.get('check')}: category {e.get('category')!r} isn't one to write by hand")
        require(bool(e.get("evidence")), f"explanation for {e.get('check')} {e.get('periods')}: no evidence key")
        require(bool(e.get("periods")), f"explanation for {e.get('check')}: no periods")
        out.append(Explanation(e["check"], tuple(e["periods"]), e["category"], e["evidence"], e.get("finding", "")))
    return out


def explain(check: str, period: str, explanations: list[Explanation]) -> Explanation | None:
    found = [e for e in explanations if e.check == check and period in e.periods]
    require(len(found) <= 1, f"{check} {period}: explained twice")
    return found[0] if found else None
