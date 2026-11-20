"""Figures typed into the site's text, checked against each build's data.

The site check (`site/src/lib/quoted-figures.mjs`) makes every figure with a unit in the text
look-at-once: it is listed in `site/src/i18n/figures-allow.json` with its kind. A figure of kind
`past` is a measurement of a period that has ended, and a publisher's revision can still change
it; once builds go live without a person reading them, a revised figure would stay wrong in the
text. So each `past` entry says, figure by figure (its English figures, in order), where the
figure comes from:

- a series the build exports: the release step `check-figures` recomputes it from the site's
  data files and fails the build when, rounded as written, it no longer reads the same;
- anything else (survey microdata, a one-off study, an item index we don't export): the archived
  datasets it rests on, with the reason it can't be recomputed. A build in which one of them
  changed waits for the owner (`release_decision`), who reads the sentence again.

A figure's data check is a small JSON object:

    {"figure": "2.5 points", "m1": {"setting": "default", "grouping": "B", "group": "Q1-Q5",
     "unit": "RCH_A_GAP", "period": "2022-04"}, "peak": true}

`m1`: a module 1 rate series (`downloads/<setting>/m1_rates.parquet`; "default" is the default
setting's slug); `m5`: a consistency download (`downloads/<name>.csv`) with `source`. Then
`period` picks one value; `minus` (fields that differ) subtracts another series of the same
kind; `change_from` turns the value into a percent change from that period; `most` takes the
largest absolute value over every period (an "at most" sentence); `abs` compares the size only
("fell by 8%"); `peak` also requires the period to be the series' largest value. `largest_of`
(a list of such checks, without `figure`) takes the largest of their values: "up to 0.9 points
between rules" is the largest over every pair of rules.
"""

from __future__ import annotations

import csv
import json
import re
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import duckdb

PAST = "past"
SPEC = ("m1", "m5", "largest_of")
# The number in a figure as the English text writes it: sign, digits, a decimal point.
NUMBER = re.compile(r"([+\-−]?)(\d[\d ]*(?:\.\d+)?)")


def written(figure: str) -> tuple[Decimal, int]:
    """The figure's number and its decimals, e.g. "−1.6 points" -> (-1.6, 1)."""
    m = NUMBER.search(figure)
    if m is None or re.search(r"\d\s?[–-]\s?\d", figure):
        raise ValueError(f"{figure!r}: not one number (a range can't be checked against one value)")
    digits = m[2].replace(" ", "")
    number = Decimal(digits) * (-1 if m[1] in "-−" and m[1] else 1)
    return number, len(digits.split(".")[1]) if "." in digits else 0


def rounded(value: float, decimals: int) -> Decimal:
    """Rounded half up, as figures are written (Python's round() rounds half to even)."""
    return Decimal(repr(value)).quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_UP)


class Data:
    """The site's data files (the `data` folder an export writes), read as each check needs them."""

    def __init__(self, root: Path):
        self.root = root / "v1" / "gr"
        self._default = None

    def default(self) -> str:
        if self._default is None:
            settings = json.loads((self.root / "m1" / "latest" / "settings.json").read_text(encoding="utf-8"))
            self._default = settings["default"]
        return self._default

    def series(self, spec: dict) -> dict[str, float]:
        """{period: value} of the series a spec names (its `period` aside)."""
        if "m1" in spec:
            s = spec["m1"]
            setting = self.default() if s["setting"] == "default" else s["setting"]
            path = self.root / "m1" / "latest" / "downloads" / setting / "m1_rates.parquet"
            rows = duckdb.connect().execute(
                f"""SELECT ref_period, CAST(value AS DOUBLE) FROM '{path.as_posix()}'
                WHERE grouping = ? AND "group" = ? AND unit = ? ORDER BY ref_period""",
                [s["grouping"], s["group"], s["unit"]],
            )
            return dict(rows.fetchall())
        path = self.root / "m5" / "latest" / "downloads" / f"{spec['m5']}.csv"
        with path.open(encoding="utf-8", newline="") as f:
            return {r["period"]: float(r["value"]) for r in csv.DictReader(f) if r["source"] == spec["source"]}


def _with(spec: dict, changes: dict) -> dict:
    """The spec with some fields changed (`minus`): the series' own fields, one level down."""
    key = "m1" if "m1" in spec else None
    if key:
        return {**spec, key: {**spec[key], **changes}}
    return {**spec, **changes}


def value(data: Data, spec: dict) -> tuple[float, str | None]:
    """The value a check computes, and the period it is for (None for a largest-over-periods)."""
    if "largest_of" in spec:
        return max(value(data, s)[0] for s in spec["largest_of"]), None
    series = data.series(spec)
    if "minus" in spec:
        other = data.series(_with(spec, spec["minus"]))
        series = {p: v - other[p] for p, v in series.items() if p in other}
    if spec.get("most"):
        if not series:
            raise KeyError("no values")
        period = max(series, key=lambda p: abs(series[p]))
        return abs(series[period]), None
    period = (spec["m1"] if "m1" in spec else spec)["period"]
    if period not in series:
        raise KeyError(f"no value for {period}")
    v = series[period]
    if "change_from" in spec:
        v = (v / series[spec["change_from"]] - 1) * 100
    if spec.get("peak") and period != max(series, key=series.get):
        top = max(series, key=series.get)
        raise KeyError(f"the series peaks at {top} ({series[top]:.2f}), not at {period}")
    return v, period


def check(data_dir: Path, entries: list[dict]) -> list[str]:
    """Problems with the `past` figures the data can recompute; none: the text still reads true."""
    data = Data(data_dir)
    problems = []
    for e in entries:
        if e.get("kind") != PAST:
            continue
        for spec in e.get("checks", []):
            if not any(k in spec for k in SPEC):
                continue
            figure = spec["figure"]
            want, decimals = written(figure)
            try:
                got, _ = value(data, spec)
            except (KeyError, FileNotFoundError, duckdb.Error) as exc:
                why = exc.args[0] if isinstance(exc, KeyError) and exc.args else exc  # no quotes around it
                problems.append(f"{e['id']}: {figure}: can't be recomputed ({why})")
                continue
            if spec.get("abs"):
                got, want = abs(got), abs(want)
            if rounded(got, decimals) != want:
                problems.append(f"{e['id']}: the text says {figure}, the data now say {rounded(got, decimals)}")
    return problems


def problems_in_list(entries: list[dict]) -> list[str]:
    """What's wrong with the list itself: every `past` entry must say where each English figure
    comes from, in order, either as a data check or as the datasets it rests on with a reason."""
    out = []
    for e in entries:
        if e.get("kind") != PAST:
            continue
        figures = [c.get("figure") for c in e.get("checks", [])]
        if figures != e.get("en", []):
            out.append(f"{e['id']}: its checks name {figures}, its English figures are {e.get('en', [])}")
        for c in e.get("checks", []):
            if any(k in c for k in SPEC):
                try:
                    written(c["figure"])
                except ValueError as exc:
                    out.append(f"{e['id']}: {exc}")
            elif not (c.get("sources") and c.get("reason")):
                out.append(f"{e['id']}: {c.get('figure')}: neither a data check nor sources with a reason")
    return out


def sources(entries: list[dict]) -> dict[str, list[str]]:
    """{entry id: the archived datasets its figures rest on} for figures the data can't recompute.
    A name ending in "*" is a prefix."""
    out: dict[str, list[str]] = {}
    for e in entries:
        if e.get("kind") != PAST:
            continue
        names = sorted({s for c in e.get("checks", []) for s in c.get("sources", [])})
        if names:
            out[e["id"]] = names
    return out


def changed_sources(quoted: dict[str, list[str]], changed: set[str]) -> list[str]:
    """For each entry whose sources include a changed dataset: which one, as a hold reason."""

    def hit(name: str, dataset: str) -> bool:
        return dataset.startswith(name[:-1]) if name.endswith("*") else dataset == name

    out = []
    for entry, names in sorted(quoted.items()):
        moved = sorted({d for d in changed for n in names if hit(n, d)})
        if moved:
            out.append(f"the text's figures in {entry} rest on {', '.join(moved)}, which changed: read them again")
    return out


def load(allow_list: Path) -> list[dict]:
    return json.loads(allow_list.read_text(encoding="utf-8"))["entries"]
