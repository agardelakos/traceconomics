"""Standard errors of the spending shares: a rescaled bootstrap over the survey's primary sampling units.

The survey is a stratified sample of areas (primary sampling units, `HA07`), with several
households interviewed in each. Households in one area are alike, so the uncertainty comes from
which areas were drawn, not which households: the bootstrap resamples areas, within each stratum.

Each replicate (Rao and Wu 1988, in the form that rescales the weights, Rao, Wu and Yue 1992;
both as described in Preston 2009, section 3):

    in every stratum h with n_h areas, draw n_h - 1 areas with replacement;
    area i drawn r_hi times gets the weight factor r_hi * n_h / (n_h - 1).

That is the general rescaled weight (1 - L + L * (n_h / m_h) * r_hi) with m_h = n_h - 1 and
L = sqrt(m_h (1 - f_h) / (n_h - 1)) = 1, taking the first-stage sampling fraction f_h as
negligible (an assumption: some 600-1,000 areas drawn from the whole country). Because the
weights, not the data, are rescaled, the method also suits statistics built on quantiles,
which ours are: in every replicate the households are ranked again and the quintile cut points
move. The standard error is the spread of the replicates' estimates around their mean
(divisor B - 1).

Caveats (Eurostat precision handbook 2013): the bootstrap "has not been adequately tested for
large-scale, complex surveys", and the published weights are calibrated, which a replicate
can't redo without the calibration totals. So the errors are a lower bound.

Per year the design is what the files support:
- strata `HA06` and areas `HA07`: the full design;
- no strata column (2008): the region `HA08` stands in for the strata, labelled an approximation;
- no area column (2017-2019): no standard errors, with that reason. They are never invented.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from traceconomics.checks import require
from traceconomics.local.groups import RANKED, quintile_matrix, ranking
from traceconomics.local.puf import Survey
from traceconomics.local.shares import PUBLISHED, basket, group_shares, memberships

REPLICATES = 1000
SEED = 20261019          # fixed, so a rerun gives the same errors; the year is mixed in per survey
CHUNK = 100              # replicates computed at a time, to bound memory
HIGH_RSE = 0.25          # relative standard error at which a share is flagged (BLS/ABS practice)


@dataclass
class Design:
    status: str                      # "full", "approximate" or "unavailable"
    note: str
    strata: np.ndarray | None = None
    areas: np.ndarray | None = None


def design(survey: Survey) -> Design:
    h = survey.households
    if survey.design == "no-clusters":
        return Design("unavailable", f"{survey.year}: the files have no primary sampling unit (HA07), "
                                     "so the areas can't be resampled")
    if survey.design == "no-strata":
        status, note, strata = "approximate", (f"{survey.year}: no stratum column; the region (HA08) "
                                              "stands in for the strata"), h.region
    else:
        status, note, strata = "full", f"{survey.year}: strata HA06, areas HA07", h.stratum
    strata, areas = strata.astype(str).to_numpy(), h.cluster.astype(str).to_numpy()
    pairs = pd.DataFrame({"s": strata, "a": areas}).drop_duplicates()
    require(pairs.a.is_unique, f"{survey.year}: an area sits in more than one stratum")
    small = pairs.groupby("s").size()
    require((small >= 2).all(), f"{survey.year}: strata with a single area: {sorted(small[small < 2].index)[:5]}")
    return Design(status, note, strata, areas)


def replicate_factors(d: Design, replicates: int, rng: np.random.Generator) -> np.ndarray:
    """households x replicates: each household's weight factor, from its area's draws."""
    area_index, area_codes = pd.factorize(d.areas, sort=True)
    stratum_of_area = pd.Series(d.strata).groupby(area_index).first().to_numpy()
    factors = np.empty((len(area_codes), replicates))
    for stratum in sorted(set(stratum_of_area)):
        mine = np.flatnonzero(stratum_of_area == stratum)
        n = len(mine)
        draws = rng.multinomial(n - 1, np.full(n, 1 / n), size=replicates)     # replicates x n
        factors[mine] = draws.T * n / (n - 1)
    return factors[area_index]


def standard_errors(survey: Survey, groups: pd.DataFrame, replicates: int = REPLICATES,
                    seed: int = SEED, spending: str = "purchases") -> tuple[Design, pd.DataFrame]:
    """(the design used, a table grouping, group, imputed_rent, code, se) for the published
    groupings. The table is empty when the design is unavailable."""
    d = design(survey)
    if d.status == "unavailable":
        return d, pd.DataFrame(columns=["grouping", "group", "imputed_rent", "code", "se"])
    rng = np.random.default_rng([seed, survey.year])
    factors = replicate_factors(d, replicates, rng)
    w = survey.households.weight.to_numpy(float)
    values, size = ranking(survey)
    size = size.to_numpy(float)
    ids = survey.households.hh
    fixed = [(g, label, m) for g, label, m in memberships(groups, PUBLISHED) if g not in RANKED]
    ranked = [g for g in PUBLISHED if g in RANKED]

    trees, xs = zip(*(basket(survey, spending, option) for option in (1, 2)))
    point = {}        # the estimate, from the full-sample weights
    for t, x in zip(trees, xs):
        for g, label, m in memberships(groups, PUBLISHED):
            point[(g, label, t.option)] = group_shares(x, (w * m)[:, None], t)[:, 0]
    # Sums of deviations from the estimate, and of their squares, per cell.
    s1 = {k: np.zeros_like(v) for k, v in point.items()}
    s2 = {k: np.zeros_like(v) for k, v in point.items()}

    for start in range(0, replicates, CHUNK):
        rw = w[:, None] * factors[:, start:start + CHUNK]                    # households x chunk
        members = [(g, label, m[:, None]) for g, label, m in fixed]
        for g in ranked:
            value, by_people, parts, prefix = RANKED[g]
            basis = rw * np.nan_to_num(size)[:, None] if by_people else rw
            q = quintile_matrix(values[value], basis, ids, parts)
            members += [(g, f"{prefix}{k}", q == k) for k in range(1, parts + 1)]
        for t, x in zip(trees, xs):
            for g, label, m in members:
                key = (g, label, t.option)
                if key not in point:
                    continue
                dev = group_shares(x, rw * m, t) - point[key][:, None]
                s1[key] += dev.sum(axis=1)
                s2[key] += (dev ** 2).sum(axis=1)

    rows = []
    for t in trees:
        for g, label, _ in memberships(groups, PUBLISHED):
            key = (g, label, t.option)
            var = (s2[key] - s1[key] ** 2 / replicates) / (replicates - 1)
            for code, v in zip(t.codes, var):
                rows.append({"grouping": g, "group": label, "imputed_rent": t.option, "code": code,
                             "se": float(np.sqrt(max(v, 0.0)))})
    return d, pd.DataFrame(rows)


def with_errors(shares: pd.DataFrame, errors: pd.DataFrame, d: Design) -> pd.DataFrame:
    """The shares table plus se, rse (se / share) and high_rse (rse of 25% or more), and the design
    status. Without a design the error columns are empty."""
    key = ["grouping", "group", "imputed_rent", "code"]
    out = shares.merge(errors, on=key, how="left", validate="one_to_one")
    published = out.grouping.isin(PUBLISHED)
    require(d.status == "unavailable" or out.se[published].notna().all(), "shares without a standard error")
    out["rse"] = out.se / out.share.where(out.share > 0)
    out["high_rse"] = (out.rse >= HIGH_RSE).where(out.rse.notna(), pd.NA)
    out["se_design"] = d.status
    return out
