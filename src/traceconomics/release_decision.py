"""Whether a passing release build may go live by itself, and if not, why.

A build is promoted to production without the owner only when nothing but the publishers' data
changed since the build production serves, and the numbers moved as they normally do. Each rule
below that fails is a reason to hold the build; a held build waits for the owner, exactly as every
build did before, so a hold costs one promote by hand and nothing else.

- **The same code.** The build's git commit equals the production build's. Code reaches the
  machine only through a deploy, so a deploy's first build always holds, and so does a build whose
  commit can't be read.
- **The same own inputs.** The tables we build ourselves from the survey microdata (archive
  source `oet-local`) are the same archived files as in the production build, and no dataset
  appeared or went. A rebuilt table changes the numbers without any publisher releasing anything.
- **Something new.** At least one publisher file is new; otherwise there is nothing to publish.
- **No revised value.** The default setting's annual rates that production published are all
  unchanged. Archived copies one release apart (ELSTAT's CPI tables 07 and 05, Eurostat's HICP
  for Greece, 2026-10 to 2026-11) revised none of about 555,000 values, so a revision is itself
  unusual and worth a look, whatever its size.
- **No month beyond a group's record.** For each household group, the gap between its annual rate
  and all households' rate, and the change of that gap from the month before, stay within the
  largest the group has had in the published history (2009 on; records from 0.39 to 3.39 points for
  the gap, 0.23 to 1.45 for its change, mostly set in 2022). Judged this way against the history so
  far, no month of 2023 to 2026 would have held. A month like 2022's holds for a look, which is the
  point. The records are read from production's own outputs, so a month the owner promotes after a
  hold becomes part of the history.
- **The text's figures still stand.** A past figure typed into the site's text that the data can't
  recompute names the archived datasets it rests on (`quoted_figures`); a change to one of them
  holds the build, so a person reads the sentence again. (Figures the data can recompute are
  checked by the build itself, step `check-figures`.)
- **Production is what its record says.** The production address serves the production build's
  own files; otherwise the comparison would be with the wrong build.

The default setting is the one headlines use: the limits apply to it only.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path

from traceconomics import quoted_figures
from traceconomics.archive.store import read_jsonl

PROMOTE, HOLD = "promote", "hold"
OFF, SHADOW, ON = "off", "shadow", "on"
MODES = (OFF, SHADOW, ON)
# Each build's record of the archived files its store held, next to its release.json.
INPUTS = "inputs.json"
# The archive source of the tables we build ourselves from the survey microdata.
OWN = "oet-local/"
# The headline setting (as in the site's defaults), annual rates.
DEFAULT_SETTING = (
    "spending = 'purchases' AND imputed_rent = 'excluded' AND price_source = 'cpi' "
    "AND weights_timing = 'N' AND tutoring = 'priced' AND unit = 'RCH_A'"
)
ALL = ("all", "all")
SURVEY_YEAR = re.compile(r"-(\d{4})$")


@dataclass
class Decision:
    """Whether a build is promoted or held, why, and the production build it was compared with."""

    verdict: str
    reasons: list[str] = field(default_factory=list)
    production: str | None = None  # the build compared with

    def as_dict(self) -> dict:
        """The decision as a plain dict."""
        return asdict(self)


def store_inputs(store_dir: Path) -> dict[str, list[str]]:
    """Every archived file the store has read: {archive dataset: [sha256, ...]}, sorted."""
    from traceconomics.store.build import LOADED

    files: dict[str, set[str]] = defaultdict(set)
    path = Path(store_dir) / LOADED
    for rec in read_jsonl(path) if path.is_file() else []:
        files[rec["archive_dataset"]].add(rec["sha256"])
    return {ds: sorted(shas) for ds, shas in sorted(files.items())}


def input_changes(old: dict[str, list[str]], new: dict[str, list[str]]) -> dict[str, list[str]]:
    """Files and datasets in one inputs record and not the other, as "dataset sha12" and names."""

    def files(rec):
        return {f"{ds} {sha[:12]}" for ds, shas in rec.items() for sha in shas}

    return {
        "new_files": sorted(files(new) - files(old)),
        "gone_files": sorted(files(old) - files(new)),
        "new_datasets": sorted(set(new) - set(old)),
        "gone_datasets": sorted(set(old) - set(new)),
    }


def _month_before(period: str) -> str:
    y, m = int(period[:4]), int(period[5:7])
    return f"{y - 1}-12" if m == 1 else f"{y}-{m - 1:02d}"


def _gaps(rows) -> dict[tuple[str, str], dict[str, float]]:
    """{(grouping, group): {month: its annual rate minus all households'}} for the months both have."""
    rates: dict[tuple[str, str], dict[str, float]] = defaultdict(dict)
    for grouping, group, period, value in rows:
        rates[(grouping, group)][period] = value
    every = rates.pop(ALL, {})
    return {g: {p: v - every[p] for p, v in sorted(series.items()) if p in every} for g, series in rates.items()}


def _rows(rates_file: Path) -> list[tuple]:
    import duckdb

    con = duckdb.connect()
    # The outputs keep every column as text, the value too (its full digits): read as a number here.
    return con.execute(
        f'SELECT grouping, "group", ref_period, v FROM (SELECT *, TRY_CAST(value AS DOUBLE) AS v '
        f"FROM '{rates_file.as_posix()}') WHERE {DEFAULT_SETTING} AND coicop18 = 'TOTAL' AND v IS NOT NULL "
        'ORDER BY grouping, "group", ref_period'
    ).fetchall()


def beyond_records(old_rows, new_rows) -> list[str]:
    """Each new month in which a group's gap to all households goes beyond its published record.

    Both the gap and its change from the month before are checked against the group's largest
    in the old (published) history.
    """
    old, new = _gaps(old_rows), _gaps(new_rows)
    out = []
    for g, series in sorted(new.items()):
        name = "/".join(g)
        history = old.get(g, {})
        fresh = [p for p in series if p not in history]
        if not fresh:
            continue
        if not history:
            out.append(f"{name}: a group with no published history")
            continue
        gap_record = max(abs(v) for v in history.values())
        steps = [abs(v - history[_month_before(p)]) for p, v in history.items() if _month_before(p) in history]
        step_record = max(steps, default=0.0)
        for p in fresh:
            gap = series[p]
            if abs(gap) > gap_record:
                out.append(f"{name} {p}: gap to all households {gap:+.2f} points, beyond its record {gap_record:.2f}")
            before = series.get(_month_before(p))
            if before is not None and abs(gap - before) > step_record:
                out.append(
                    f"{name} {p}: the gap moved {gap - before:+.2f} points in a month, beyond its record {step_record:.2f}"
                )
    return out


def beyond_records_in(old_rates: Path, new_rates: Path) -> list[str]:
    """`beyond_records` for two module 1 rates files: production's (old) and this build's (new)."""
    return beyond_records(_rows(old_rates), _rows(new_rates))


def decide(
    *,
    production: str | None,
    commit: str | None,
    production_commit: str | None,
    inputs: dict | None,
    production_inputs: dict | None,
    changes: dict,
    beyond: list[str],
    served_problem: str | None,
    quoted: dict[str, list[str]] | None = None,
) -> Decision:
    """Promote, or hold with every reason that applies (see the module's docstring)."""
    if production is None:
        return Decision(HOLD, ["production serves no build on record to compare with"])
    reasons = []
    if served_problem:
        reasons.append(f"production doesn't serve its recorded build {production} ({served_problem})")
    if not commit or not production_commit:
        reasons.append("a git commit is unknown (this build's or production's), so a code change can't be ruled out")
    elif commit != production_commit:
        reasons.append(f"the code changed: commit {commit[:12]}, production's build {production_commit[:12]}")
    if inputs is None or production_inputs is None:
        reasons.append("an inputs record is missing (this build's or production's), so the inputs can't be compared")
    else:
        diff = input_changes(production_inputs, inputs)
        own = [x for x in diff["new_files"] + diff["gone_files"] if x.startswith(OWN)]
        if own:
            reasons.append("our own tables changed: " + ", ".join(own))
        years = sorted(
            m[1] for ds in diff["new_datasets"] if ds.startswith(OWN) and (m := SURVEY_YEAR.search(ds)) is not None
        )
        if years:
            reasons.append("a new survey year: " + ", ".join(sorted(set(years))))
        if diff["new_datasets"]:
            reasons.append("datasets that production's build didn't have: " + ", ".join(diff["new_datasets"]))
        gone = [x for x in diff["gone_files"] if not x.startswith(OWN)]
        if gone:
            reasons.append("archived files gone since production's build: " + ", ".join(gone))
        if diff["gone_datasets"]:
            reasons.append("datasets gone since production's build: " + ", ".join(diff["gone_datasets"]))
        if not diff["new_files"] and not diff["gone_files"]:
            reasons.append("nothing new: no archived file differs from production's build")
        # A figure typed into the text that the data can't recompute names the datasets it
        # rests on (figures-allow.json): when one changes, a person reads the sentence again.
        moved = {x.split(" ")[0] for x in diff["new_files"] + diff["gone_files"]}
        reasons += quoted_figures.changed_sources(quoted or {}, moved)
    if not changes or changes.get("first_release"):
        reasons.append("no comparison with production's published rates")
    elif changes.get("revised_values"):
        reasons.append(
            f"{changes['revised_values']} published values revised (largest {changes['largest_revision_pp']:.2f} points)"
        )
    reasons += beyond
    return Decision(HOLD if reasons else PROMOTE, reasons, production)
