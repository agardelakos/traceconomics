"""Error bands for the group series: how much the rates could move with another sample of households.

For each survey, the bootstrap's replicates (`bootstrap`, the same draws that give the shares
their standard errors) each give a full set of group shares. Each replicate set goes through the
same steps as the published series: the same pricing of each item, the same price-updating to
December of the year before, the same chaining at December. The spread of the replicates'
annual rates is the standard error. The Q1-Q5 gap is computed within each replicate (both
groups from the same draw), so the two groups' correlation is kept.

Different surveys are independent samples, so replicate r of one survey is paired with replicate
r of the next. A rate that depends on a year whose survey has no usable design (no sampling
areas in the file, 2017-2019) gets no band: its months are reported as unavailable, never given a
band that leaves out a source of uncertainty. Which months those are depends on the
weights-timing rule, since it decides which survey each year uses.

Leaving tutoring out (from 2026) is done within each replicate, with the group's split from the
2024 survey held at its estimate.

The bands cover the sampling of households only: not the sampling error of the price indices
themselves (unpublished), so they are a lower bound.
"""

from __future__ import annotations

import io
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime

import numpy as np
import pandas as pd

from traceconomics import __version__
from traceconomics.archive.store import Archive
from traceconomics.checks import require
from traceconomics.engine.chain import _price_ratio, link_month, months
from traceconomics.local import bootstrap, mapping, puf
from traceconomics.local.groups import RANKED, assign, quintile_matrix, ranking
from traceconomics.local.shares import basket, group_shares, memberships
from traceconomics.module1.index import Series
from traceconomics.module1.prices import update_factor
from traceconomics.module1.weights_used import BY_LEVEL, CODED_2018_FROM, EXCLUDED, NOT_BY_LEVEL, TUTORING_EXCLUDED_FROM

SOURCE = "oet-local"
DATASET = "hbs-bands-gr"
GAP = ("Q1", "Q5")


def replicate_leaf_shares(survey, groups: pd.DataFrame, wanted, spending: str = "purchases",
                          replicates: int = bootstrap.REPLICATES, seed: int = bootstrap.SEED, option: int = 1):
    """(design, leaves, {(grouping, group): leaves x replicates shares}); None shares without a design.
    `option`: the imputed-rent option (1 drops it, 2 keeps it)."""
    d = bootstrap.design(survey)
    tree, x = basket(survey, spending, option)
    leaf_rows = [tree.codes.index(c) for c in tree.leaves]
    if d.status == "unavailable":
        return d, tree.leaves, None
    rng = np.random.default_rng([seed, survey.year])          # the same draws as the standard errors
    factors = bootstrap.replicate_factors(d, replicates, rng)
    w = survey.households.weight.to_numpy(float)
    values, size = ranking(survey)
    size = np.nan_to_num(size.to_numpy(float))
    ids = survey.households.hh
    fixed = {(g, label): m for g, label, m in memberships(groups) if (g, label) in wanted and g not in RANKED}
    out = {k: np.empty((len(tree.leaves), replicates)) for k in wanted}
    for start in range(0, replicates, bootstrap.CHUNK):
        cols = slice(start, start + bootstrap.CHUNK)
        rw = w[:, None] * factors[:, cols]
        members = {k: m[:, None] for k, m in fixed.items()}
        for g in {g for g, _ in wanted if g in RANKED}:
            value, by_people, parts, prefix = RANKED[g]
            q = quintile_matrix(values[value], rw * size[:, None] if by_people else rw, ids, parts)
            members.update({(g, f"{prefix}{k}"): q == k for k in range(1, parts + 1) if (g, f"{prefix}{k}") in wanted})
        for k, m in members.items():
            out[k][:, cols] = group_shares(x, rw * m, tree)[leaf_rows]
    return d, tree.leaves, out


def without_tutoring(leaves: list[str], reps: np.ndarray, fraction: float | None) -> np.ndarray:
    """The replicates' shares with tutoring left out, as `weights_used.exclude_tutoring` does for the
    estimate: all of 10.5, and, for a survey before COICOP 2018 (`fraction` given), the rest of the
    group's tutoring from 10.1 and 10.2 in proportion."""
    reps = reps.copy()
    nbl = [i for i, c in enumerate(leaves) if c.startswith(NOT_BY_LEVEL)]
    lvl = [i for i, c in enumerate(leaves) if c.startswith(BY_LEVEL)]
    s_nbl = reps[nbl].sum(axis=0)
    if fraction is not None and lvl:
        s_lvl = reps[lvl].sum(axis=0)
        rest = np.maximum(fraction * (s_lvl + s_nbl) - s_nbl, 0.0)
        safe = np.where(s_lvl > 0, s_lvl, 1.0)
        reps[lvl] *= np.where(s_lvl > 0, 1 - rest / safe, 1.0)
    reps[nbl] = 0.0
    return reps


@dataclass
class Bands:
    # (grouping, group, unit) -> period -> se, for one setting
    se: dict[tuple[str, str, str], dict[str, float]] = field(default_factory=dict)
    unavailable_years: dict[tuple[str, str], set[int]] = field(default_factory=dict)


def series_rates(index: dict, start: str):
    periods = sorted(p for p in index if p >= start)
    annual = {p: (index[p] / index[f"{int(p[:4]) - 1}{p[4:]}"] - 1) * 100
              for p in periods if f"{int(p[:4]) - 1}{p[4:]}" in index}
    avg = {}
    for y in sorted({int(p[:4]) for p in periods}):
        cur = [index.get(f"{y}-{m:02d}") for m in range(1, 13)]
        prev = [index.get(f"{y - 1}-{m:02d}") for m in range(1, 13)]
        if all(v is not None for v in cur + prev):
            avg[str(y)] = (sum(cur) / sum(prev) - 1) * 100
    return annual, avg


def bands(series: list[Series], blocks, replicate_sets: dict[int, tuple], replicates: int) -> Bands:
    """Standard errors of each series' annual and annual-average rates, and of the Q1-Q5 gap of every
    quintile grouping. The series must share one setting (price source, imputed rent, spending).

    replicate_sets: {survey year: (leaves, {(grouping, group): leaves x R} or None)}."""
    result = Bands()
    rates = {}
    ratio_cache: dict[tuple, float] = {}
    for s in series:
        first = s.schedule[0].year
        index = {link_month(first): np.full(replicates, 100.0)}
        unavailable = set()
        for entry in s.schedule:
            y, used = entry.year, s.used[entry.year]
            leaves, sets = replicate_sets[entry.survey]
            reps = None if sets is None else sets.get((s.grouping, s.group))
            codes = sorted(used.weights)
            if reps is None:
                unavailable.add(y)
                w = np.repeat(np.array([used.weights[c] for c in codes])[:, None], replicates, axis=1)
            else:
                pos = {c: i for i, c in enumerate(leaves)}
                missing = [c for c in codes if c not in pos]
                require(not missing, f"{y} {s.grouping}/{s.group}: weights for codes the survey lacks: {missing[:5]}")
                if s.options.get("tutoring") == EXCLUDED and y >= TUTORING_EXCLUDED_FROM:
                    reps = without_tutoring(leaves, reps, s.tutoring_split if entry.survey < CODED_2018_FROM else None)
                if entry.survey >= y:
                    f = np.ones(len(codes))          # same-year weights: nothing to update from
                else:
                    f = np.array([update_factor(blocks, used.price_with.get(c, c), entry.survey, y)[0] for c in codes])
                raw = np.vstack([reps[pos[c]] for c in codes]) * f[:, None]
                w = raw / raw.sum(axis=0)
            block, base = blocks[y], link_month(y)
            for period in months(y):
                if period not in s.chained.links:
                    continue
                ratios = []
                for c in codes:
                    k = (period, used.price_with.get(c, c))
                    if k not in ratio_cache:
                        ratio_cache[k] = _price_ratio(block, k[1], period, base)[0]
                    ratios.append(ratio_cache[k])
                index[period] = index[base] * (np.array(ratios) @ w)
        result.unavailable_years[(s.grouping, s.group)] = unavailable
        rates[(s.grouping, s.group)] = (series_rates(index, f"{first}-01"), unavailable)

    def depends_on(unavailable, year: int) -> bool:
        return bool({year, year - 1} & unavailable)

    for (g, label), ((annual, avg), unavailable) in rates.items():
        result.se[(g, label, "RCH_A")] = {p: float(np.std(v, ddof=1)) for p, v in annual.items()
                                         if not depends_on(unavailable, int(p[:4]))}
        result.se[(g, label, "RCH_A_AVG")] = {p: float(np.std(v, ddof=1)) for p, v in avg.items()
                                             if not depends_on(unavailable, int(p))}
    for g in sorted({g for g, _ in rates}):
        lo, hi = rates.get((g, GAP[0])), rates.get((g, GAP[1]))
        if not (lo and hi):
            continue
        (la, lv), lu = lo
        (ha, hv), hu = hi
        both = lu | hu
        gap = f"{GAP[0]}-{GAP[1]}"
        result.se[(g, gap, "RCH_A_GAP")] = {p: float(np.std(la[p] - ha[p], ddof=1)) for p in la
                                           if p in ha and not depends_on(both, int(p[:4]))}
        result.se[(g, gap, "RCH_A_AVG_GAP")] = {p: float(np.std(lv[p] - hv[p], ddof=1)) for p in lv
                                               if p in hv and not depends_on(both, int(p))}
    return result


def run(archive: Archive, con, replicates: int = bootstrap.REPLICATES, only=None, log=print) -> dict:
    """Compute the bands for every combination in `only` (default: all) and archive them, in one
    file, as `oet-local/hbs-bands-gr`. One spending concept and imputed-rent option at a time:
    their replicate shares serve every price source, timing rule and tutoring option."""
    from traceconomics.module1 import combinations

    only = only or combinations.settings()
    wanted = set(combinations.GROUPS)
    rows, designs, unavailable = [], {}, {}
    for spending, rent in sorted({(s["spending"], s["imputed_rent"]) for s in only}):
        these = [s for s in only if (s["spending"], s["imputed_rent"]) == (spending, rent)]
        built = list(combinations.iterate(con, archive, only=these))
        surveys = sorted({e.survey for _, series, _ in built for s in series for e in s.schedule})
        sets = {}
        for year in surveys:
            survey = puf.read(archive, year)
            groups = assign(survey)
            d, leaves, reps = replicate_leaf_shares(mapping.to_2018(survey), groups, wanted, spending, replicates,
                                                    option=2 if rent == "included" else 1)
            sets[year] = (leaves, reps)
            designs[year] = d.status
        log(f"{spending}/{rent}: replicate shares for {len(surveys)} surveys")
        for setting, series, blocks in built:
            b = bands(series, blocks[setting["price_source"]], sets, replicates)
            unavailable[combinations.label(setting)] = sorted(set().union(*b.unavailable_years.values()))
            for (g, label, unit), values in sorted(b.se.items()):
                for period, se in sorted(values.items()):
                    rows.append({"geo": "GR", "grouping": g, "group": label, "spending": spending,
                                 "imputed_rent": rent, "price_source": setting["price_source"],
                                 "weights_timing": setting["weights_timing"], "tutoring": setting["tutoring"],
                                 "unit": unit, "ref_period": period, "se": f"{se:.6g}"})
            log(f"  {combinations.label(setting)}: done")
        del built, sets
    table = pd.DataFrame(rows)
    head = ["Standard errors of the group series' rates from the household budget survey bootstrap; aggregates only.",
            "provenance: " + json.dumps({"replicates": replicates, "seed": bootstrap.SEED, "designs": designs,
                                         "unavailable_index_years": unavailable,
                                         "code_version": __version__}, sort_keys=True)]
    buf = io.StringIO()
    buf.write("".join(f"# {line}\n" for line in head))
    table.to_csv(buf, index=False, lineterminator="\n")
    r = archive.store_bytes(SOURCE, DATASET, buf.getvalue().encode("utf-8"), url=None, retrieved_at=datetime.now(UTC),
                            ext=".csv", kind="local", extra={"original_name": f"{DATASET}.csv", "note": "built locally"})
    return {"status": r.status, "rows": len(table), "designs": designs, "unavailable_index_years": unavailable,
            "table": table}
