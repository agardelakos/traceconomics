"""Official price indices rebuilt from their own parts: the CPI from table 07, the HICP from Eurostat.

The engine's validation (`validate/`) rebuilds each all-items index from the item indices and
weights the publisher releases and compares the annual rates. Here every month of that
comparison is kept and labelled:

- the two rates agree when they are equal once rounded to one decimal, as published;
- a gap of 0.1 points is "rounding": the item indices and weights are themselves published
  rounded, so a rebuilt rate can land on the other side of a rounding boundary (see
  `validate/compare.py` for why no closer rule can be met);
- anything larger is a finding, explained only by hand (`data/m5_explanations.toml`).

The CPI is checked from 2014, when ELSTAT links its index at December as the engine does (the
years before used a fixed basket, a different method); the HICP at its finest detail from
2015, the level Eurostat publishes weights for.
"""

from __future__ import annotations

from traceconomics.module5.record import Check, Comparison, Explanation, explain
from traceconomics.validate.compare import MAX_RATE_GAP, Comparison as Validation

_EPS = 1e-9

CPI = "gr-cpi-rebuilt-items"
HICP = "gr-hicp-rebuilt-items"


def from_validation(check_id: str, validation: Validation, published: dict, rebuilt: dict,
                    explanations: list[Explanation]) -> Check:
    check = Check(check_id, "gr", "percent, one decimal", 0.0, published=published, rebuilt=rebuilt)
    for period, ours, theirs in sorted(validation.rows):
        gap = abs(round(ours, 1) - round(theirs, 1))
        if gap < _EPS:
            check.comparisons.append(Comparison(period, theirs, ours, True))
        elif gap <= MAX_RATE_GAP + _EPS:
            check.comparisons.append(Comparison(period, theirs, ours, False, "rounding"))
        else:
            e = explain(check_id, period, explanations)
            check.comparisons.append(Comparison(period, theirs, ours, False, e.category if e else "not-known",
                                                e.finding if e else ""))
    return check


def cpi(archive, explanations: list[Explanation]) -> Check:
    from traceconomics.validate import v1_cpi

    checked, _earlier, _disagreements, _files = v1_cpi.run_archive(archive)
    return from_validation(CPI, checked,
                           published={"source": "elstat:cpi07", "reference": "elstat-cpi-items", "label": "published"},
                           rebuilt={"source": "elstat:cpi07", "reference": "elstat-cpi-items", "label": "rebuilt"},
                           explanations=explanations)


def hicp(archive, archive_dir, duck, explanations: list[Explanation]) -> Check | None:
    from traceconomics.validate import v1

    paths = {}
    for name in ("prc_hicp_minr", "prc_hicp_iw"):
        rec = archive.latest("eurostat", name)
        if rec is None:
            return None
        paths[name] = archive_dir / rec["path"]
    weights, prices, official, rates = v1.load(duck, paths["prc_hicp_minr"], paths["prc_hicp_iw"], "GR")
    found = [r for r in v1.run(weights, prices, official, rates, last_year=int(max(official)[:4]))
             if r.name == "finest detail"]
    if not found:
        return None
    return from_validation(HICP, found[0],
                           published={"source": "eurostat:prc_hicp_minr", "reference": "eurostat-prc-hicp-minr", "label": "published"},
                           rebuilt={"source": "eurostat:prc_hicp_minr", "reference": "eurostat-prc-hicp-minr", "label": "rebuilt"},
                           explanations=explanations)
