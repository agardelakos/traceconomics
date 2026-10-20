"""Which periods each option covers, what is greyed out and why: built from the series themselves.

Nothing here is typed in by hand except the reasons' wording: the periods come from what each
combination actually covers, so the table can't promise a month the data don't have.

    options     per option value: the periods available, the periods greyed out (with a reason),
                and notes that apply to it
    fixed       options that are greyed out altogether until they are built
    identical   pairs of combinations that must agree, and over which periods
    series      per combination and group: periods, the survey behind each year's weights, and
                the periods that carry a footnote
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path

from traceconomics.module1.index import DEFAULT_OPTIONS, Series
from traceconomics.module1.output import FLAGS

HOSPITAL_SURVEYS = range(2008, 2015)     # the public files of these surveys leave out hospital services
LOCKDOWN_SURVEY = 2020

REASONS = {
    "rule_f_start": "Rule F takes the survey of three years before. The oldest survey with public microdata is "
                    "2008, so Rule F's weights start in 2011.",
    "rule_u_end": "Rule U takes the same year's survey. The newest survey with public microdata is {last_survey}, "
                  "so Rule U stops at {last_index}.",
    "same_before_2026": "The two tutoring options differ only from 2026, when ELSTAT's CPI stops weighting "
                        "tutoring; before that they are the same series.",
    "hospital": "The {first}-{last} household surveys' public files leave out hospital services. Putting them back "
                "changes the groups' annual-average rates by at most 0.11 pp and the Q1-Q5 gap by at most 0.07 pp "
                "(checked with the default options).",
    "lockdown": "Weights from the 2020 survey, a lockdown year with unusual spending.",
    "first_estimate": "A first estimate: the weights will be revised once, when the survey of the year before is "
                      "out.",
    "fixed_lag": "Our choice: before our archive existed, survey release dates can't be used, so Rule F is stated as "
                 "a fixed lag of three years, today's lag.",
    "less_certain": "Rests on ELSTAT's original 2008-2010 price tables, an older version of the prices.",
    "coarser_detail": "Before 2015, Eurostat's Greek HICP has item indices only for classes and groups, so the items "
                      "within one share its price movement.",
    "same_year_weights": "Same-year weights: not a Laspeyres-type index (its weights aren't from before the prices). "
                         "Shown to compare with studies made after the fact.",
    "hicp_later": "Eurostat publishes the HICP's item indices about a week after ELSTAT's CPI, so these combinations "
                  "update later in the month.",
}
FIXED = [
    {"option": "imputed_rent", "value": "user_cost", "status": "greyed",
     "text": "Imputed rent by user cost or net acquisitions: Greece has no price index for either."},
    {"option": "hh_weighting", "value": "democratic", "status": "greyed",
     "text": "Democratic weighting (every household counts equally): not built yet."},
    {"option": "income_support", "value": "shown", "status": "greyed",
     "text": "An income-support view (subsidies paid as cash): not built yet."},
]


@dataclass
class Summary:
    """What the table needs from one series (the series itself isn't kept)."""
    setting: dict
    grouping: str
    group: str
    index: tuple[str, str]
    annual: tuple[str, str] | None
    surveys: dict[int, tuple[int, str]]          # index year -> (survey, status)
    averages: tuple[int, int] | None = None      # first and last annual-average year
    footnotes: dict[str, dict] = field(default_factory=dict)

    @classmethod
    def of(cls, s: Series) -> Summary:
        rates = sorted(p for p, r in s.rates().items() if "annual" in r)
        averages = sorted(s.annual_average_rates())
        out = cls({"spending": s.spending, **s.options}, s.grouping, s.group,
                  (min(s.published), max(s.published)), (rates[0], rates[-1]) if rates else None,
                  {e.year: (e.survey, e.status) for e in s.schedule},
                  (averages[0], averages[-1]) if averages else None)
        out.footnotes = footnotes(out)
        return out


def footnotes(m: Summary) -> dict[str, dict]:
    out = {}
    hospital = [y for y, (h, _) in m.surveys.items() if h in HOSPITAL_SURVEYS]
    if hospital and m.annual:
        # A twelve-month rate up to November of the next year still includes some of the year's months.
        last = max(hospital)
        used = sorted({m.surveys[y][0] for y in hospital})
        out["hospital"] = {"annual_rates": [m.annual[0], min(f"{last + 1}-11", m.annual[1])],
                           "annual_averages": ([str(m.averages[0]), str(min(last + 1, m.averages[1]))]
                                               if m.averages else None),
                           "text": REASONS["hospital"].format(first=used[0], last=used[-1])}
    lockdown = [y for y, (h, _) in m.surveys.items() if h == LOCKDOWN_SURVEY]
    if lockdown:
        out["lockdown"] = {"index_years": lockdown, "text": REASONS["lockdown"]}
    first = [y for y, (_, status) in m.surveys.items() if status == "first"]
    if first:
        out["first_estimate"] = {"index_years": first, "text": REASONS["first_estimate"]}
    return out


def _span(summaries, attr):
    spans = [getattr(m, attr) for m in summaries if getattr(m, attr)]
    return (min(a for a, _ in spans), max(b for _, b in spans)) if spans else None


def _month_before(p: str) -> str:
    y, m = int(p[:4]), int(p[5:7])
    return f"{y - 1}-12" if m == 1 else f"{y}-{m - 1:02d}"


def _month_after(p: str) -> str:
    y, m = int(p[:4]), int(p[5:7])
    return f"{y + 1}-01" if m == 12 else f"{y}-{m + 1:02d}"


def build(summaries: list[Summary]) -> dict:
    full_index, full_annual = _span(summaries, "index"), _span(summaries, "annual")
    options: dict = {}
    names = ["spending", *DEFAULT_OPTIONS]
    for name in names:
        options[name] = {}
        for value in sorted({m.setting[name] for m in summaries}):
            these = [m for m in summaries if m.setting[name] == value]
            idx, ann = _span(these, "index"), _span(these, "annual")
            entry = {"default": value == ({"spending": "purchases", **DEFAULT_OPTIONS}[name]),
                     "index": list(idx), "annual_rates": list(ann) if ann else None, "greyed": [], "notes": []}
            if ann and ann[0] > full_annual[0]:
                code = "rule_f_start" if (name, value) == ("weights_timing", "F") else "starts_later"
                entry["greyed"].append({"annual_rates": [full_annual[0], _month_before(ann[0])],
                                        "index": [full_index[0], _month_before(idx[0])], "reason": code,
                                        "text": REASONS.get(code, "")})
            if ann and ann[1] < full_annual[1]:
                last_survey = max(h for m in these for h, _ in m.surveys.values())
                code = "rule_u_end" if (name, value) == ("weights_timing", "U") else "ends_earlier"
                entry["greyed"].append({"annual_rates": [_month_after(ann[1]), full_annual[1]],
                                        "index": [_month_after(idx[1]), full_index[1]], "reason": code,
                                        "text": REASONS.get(code, "").format(last_survey=last_survey, last_index=idx[1])})
            options[name][value] = entry
    _note(options, "weights_timing", "F", "fixed_lag")
    _note(options, "weights_timing", "U", "same_year_weights")
    _note(options, "tutoring", "excluded", "same_before_2026", annual_rates=[full_annual[0], "2025-12"])
    for source, (flag, year) in FLAGS.items():
        if source in options["price_source"]:
            code = flag.replace(" ", "_")
            _note(options, "price_source", source, code, index=[full_index[0], f"{year}-12"],
                  annual_rates=[full_annual[0], f"{year + 1}-12"])
    _note(options, "price_source", "hicp", "hicp_later")
    return {
        "periods": {"index": list(full_index), "annual_rates": list(full_annual)},
        "options": options,
        "fixed": FIXED,
        "identical": identical(summaries),
        "series": [{**m.setting, "grouping": m.grouping, "group": m.group, "index": list(m.index),
                    "annual_rates": list(m.annual) if m.annual else None,
                    "annual_averages": list(m.averages) if m.averages else None,
                    "surveys": {str(y): {"survey": h, "status": st} for y, (h, st) in sorted(m.surveys.items())},
                    "footnotes": m.footnotes} for m in summaries],
    }


def _note(options, name, value, code, **periods):
    if value in options.get(name, {}):
        options[name][value]["notes"].append({**periods, "reason": code, "text": REASONS[code]})


def identical(summaries: list[Summary]) -> list[dict]:
    """The pairs of combinations that must agree, by construction: the tutoring options before
    2026, and over every period where tutoring never enters (a series ending before 2026)."""
    out = []
    for m in summaries:
        if m.setting["tutoring"] != "excluded":
            continue
        last = m.index[1] if m.index[1] < "2026-01" else "2025-12"
        out.append({"a": {**m.setting, "grouping": m.grouping, "group": m.group},
                    "b": {**m.setting, "tutoring": "priced", "grouping": m.grouping, "group": m.group},
                    "index": [m.index[0], last], "reason": "same_before_2026"})
    return out


def write(folder: Path, table: dict) -> list[Path]:
    folder = Path(folder)
    j = folder / "availability.json"
    j.write_text(json.dumps(table, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    c = folder / "availability.csv"
    with c.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["option", "value", "default", "status", "index_from", "index_to", "annual_rates_from",
                    "annual_rates_to", "reason", "text"])
        for name, values in table["options"].items():
            for value, e in values.items():
                ann = e["annual_rates"] or ["", ""]
                w.writerow([name, value, e["default"], "available", *e["index"], *ann, "", ""])
                for g in e["greyed"]:
                    w.writerow([name, value, e["default"], "greyed", *g["index"], *g["annual_rates"], g["reason"], g["text"]])
                for n in e["notes"]:
                    w.writerow([name, value, e["default"], "note", *(n.get("index") or ["", ""]),
                                *(n.get("annual_rates") or ["", ""]), n["reason"], n["text"]])
        for e in table["fixed"]:
            w.writerow([e["option"], e["value"], False, e["status"], "", "", "", "", "", e["text"]])
    return [j, c]
