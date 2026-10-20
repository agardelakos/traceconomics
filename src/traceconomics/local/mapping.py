"""Map survey spending to COICOP 2018, the classification of the price indices from 2026 and of
the household budget survey from 2024.

Older surveys use older codes, in two lists:
- 2015-2023: ECOICOP version 1 subclasses (5 digits, e.g. 04110 actual rent);
- 2008-2014: an older national list. Its 4-digit classes are the COICOP classes, but its
  5-digit codes are numbered differently: the same number can mean something else (01112 is
  "bread" up to 2014 and "flours and other cereals" from 2015), so codes are never matched by
  number alone.

Two versioned tables (package data) carry the mapping, one row per link with its share of the
source code's spending:

- `coicop_v1_2018.csv`: ECOICOP v1 subclass -> COICOP 2018 subclass, along the links of the
  official correspondence (EU Vocabularies, ECOICOP ver. 2 to ECOICOP ver. 1). Where a v1
  subclass has several targets, its spending is split by iterative proportional fitting (RAS):
  the v1 x 2018 table, zero outside the correspondence's links, is scaled until its rows match
  Greece's 2025 HICP item weights in ECOICOP v1 and its columns the same year's weights in
  COICOP 2018 (Eurostat prc_hicp_inw and prc_hicp_iw). Both describe the same spending, so the
  fitted table is the split the two classifications agree on.
- `hbs_2008_2014_v1.csv`: national code of the 2008-2014 surveys -> ECOICOP v1 subclass. A code
  with the same number and the same label in both lists (published table 1.03 of the year and of
  2015) maps to itself. The rest of a class is pooled and split over the class's remaining v1
  subclasses by the 2015 survey's all-households spending, the nearest year in the newer list.

`build` writes both tables from the archive (correspondence, table 1.03, the 2015 survey) and the
store (the weights); `to_2018` applies them to a survey, household by household, so totals are
kept and every grouping can be computed on the result.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field, replace
from pathlib import Path

import numpy as np
import pandas as pd

from traceconomics.checks import require
from traceconomics.local.puf import Survey
from traceconomics.mapping_tables import FIELDS, OLD_TO_V1, V1_TO_2018, read

SUBCLASS = re.compile(r"^\d{5}$")
OLD_LIST_YEARS = range(2008, 2015)
BRIDGE_YEAR = 2015           # the survey whose shares split the older list's classes
WEIGHTS_YEAR = "2025"        # the year whose HICP weights exist in both classifications
MISFIT = 0.01                # a RAS group whose new-subclass totals are missed by more is flagged


# ---- applying ---------------------------------------------------------------------------------

def load(name: str) -> pd.DataFrame:
    return pd.DataFrame(read(name), columns=list(FIELDS))


def _apply(frame: pd.DataFrame, table: pd.DataFrame, what: str) -> pd.DataFrame:
    """Spending per source code -> spending per target code (same households, same totals)."""
    from traceconomics.local.shares import leaves
    keep = leaves(frame.columns)
    missing = sorted(set(keep) - set(table.from_code))
    require(not missing, f"{what}: codes with no mapping: {missing[:10]}")
    links = table[table.from_code.isin(keep)]
    matrix = links.pivot_table(index="from_code", columns="to_code", values="share", aggfunc="sum", fill_value=0.0)
    out = frame[list(matrix.index)].to_numpy(float) @ matrix.to_numpy()
    return pd.DataFrame(out, columns=list(matrix.columns), index=frame.index)


def with_parents(leaf_frame: pd.DataFrame) -> pd.DataFrame:
    """Add every parent code (2 to 4 digits) as the sum of its subclasses, as in the survey files."""
    cols = {c: leaf_frame[c] for c in leaf_frame.columns}
    for k in (4, 3, 2):
        for parent in sorted({c[:k] for c in leaf_frame.columns if len(c) > k}):
            if parent not in cols:
                cols[parent] = leaf_frame[[c for c in leaf_frame.columns if c.startswith(parent)]].sum(axis=1)
    return pd.DataFrame(cols)[sorted(cols)]


def to_2018(survey: Survey) -> Survey:
    """The same survey with spending and purchases in COICOP 2018 subclasses (and their parents)."""
    if survey.classification == "coicop2018":
        return survey
    require(survey.classification in ("ecoicop1", "hbs-gr-2008"), f"{survey.year}: unknown code list {survey.classification}")
    v1 = load(V1_TO_2018)
    old = load(OLD_TO_V1) if survey.classification == "hbs-gr-2008" else None

    def convert(frame: pd.DataFrame) -> pd.DataFrame:
        if old is not None:
            frame = with_parents(_apply(frame, old, f"{survey.year} (older national list)"))
        return with_parents(_apply(frame, v1, f"{survey.year} (ECOICOP v1)"))

    return replace(survey, classification="coicop2018", spending=convert(survey.spending),
                   purchases=convert(survey.purchases))


# ---- building ---------------------------------------------------------------------------------

def correspondence(path: Path) -> pd.DataFrame:
    """The official links at subclass level: columns v1, v2 (5 digits, no dots)."""
    raw = pd.read_csv(path, dtype=str, keep_default_na=False)
    for col in ("srcNot", "tgtNot"):
        require(col in raw.columns, f"{path.name}: no column {col}")
    pairs = raw[["srcNot", "tgtNot"]].drop_duplicates()
    pairs = pd.DataFrame({"v2": pairs.srcNot.str.replace(".", "", regex=False),
                          "v1": pairs.tgtNot.str.replace(".", "", regex=False)})
    sub = pairs[pairs.v1.str.match(SUBCLASS) & pairs.v2.str.match(SUBCLASS)].reset_index(drop=True)
    require(len(sub) > 300, f"{path.name}: only {len(sub)} subclass links")
    return sub


def subclass_weights(weights: pd.Series, subclasses) -> pd.Series:
    """Per mille per subclass. Eurostat leaves out the rows below a class or group with a single
    subclass (06300 hospital services is published as 063 only); there the nearest published
    parent's weight is the subclass's, provided the subclass is the only one under it."""
    subclasses = sorted(subclasses)
    out = {}
    for code in subclasses:
        out[code] = 0.0
        if code in weights.index:
            out[code] = float(weights[code])
            continue
        for k in (4, 3):
            parent = code[:k]
            alone = [c for c in subclasses if c.startswith(parent)] == [code]
            if parent in weights.index and alone:
                out[code] = float(weights[parent])
                break
    return pd.Series(out)


def ras(links: pd.DataFrame, rows: pd.Series, cols: pd.Series, tolerance: float = 1e-10,
        max_iter: int = 20_000) -> tuple[pd.Series, dict]:
    """Fit a table on `links` (columns v1, v2) to row totals `rows` (v1) and column totals `cols` (v2).

    Only rows and columns with a positive total take part. Each connected group of links is fitted
    on its own, with its column totals rescaled to its row total, since the two classifications'
    scopes differ a little. Where the links can't carry both sets of totals (a new subclass whose
    only sources weigh less than it does), no exact fit exists; the fitting then stops when the
    table no longer changes, and the column misfit is reported. It always ends on the rows, so each
    source's split adds up exactly. Returns the fitted cells (indexed by (v1, v2)) and a report
    with each source's group misfit (`misfit`: the largest relative column error in its group)."""
    live = links[links.v1.map(rows).fillna(0).gt(0) & links.v2.map(cols).fillna(0).gt(0)].reset_index(drop=True)
    # connected components of the bipartite link graph
    parent: dict[str, str] = {}

    def find(x):
        while parent.setdefault(x, x) != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b in zip("r" + live.v1, "c" + live.v2):
        parent[find(a)] = find(b)
    live["component"] = ["r" + v for v in live.v1]
    live["component"] = live.component.map(find)
    cells, report = [], {"components": 0, "max_col_error": 0.0, "iterations": 0, "misfit": {}}
    for _, part in live.groupby("component"):
        r_codes, c_codes = sorted(set(part.v1)), sorted(set(part.v2))
        ri = {c: k for k, c in enumerate(r_codes)}
        ci = {c: k for k, c in enumerate(c_codes)}
        i = part.v1.map(ri).to_numpy()
        j = part.v2.map(ci).to_numpy()
        r = rows[r_codes].to_numpy(float)
        c = cols[c_codes].to_numpy(float)
        c = c * r.sum() / c.sum()
        x = np.ones(len(part))
        for it in range(max_iter):
            before = x.copy()
            x *= (r / np.bincount(i, x, len(r)))[i]
            x *= (c / np.bincount(j, x, len(c)))[j]
            if np.abs(x - before).max() <= tolerance * r.sum():
                break
        x *= (r / np.bincount(i, x, len(r)))[i]          # end on the rows: each source's split is exact
        misfit = float(np.abs(np.bincount(j, x, len(c)) / c - 1).max())
        report["components"] += 1
        report["iterations"] = max(report["iterations"], it + 1)
        report["max_col_error"] = max(report["max_col_error"], misfit)
        report["misfit"].update({code: misfit for code in r_codes})
        cells.append(pd.Series(x, index=pd.MultiIndex.from_arrays([part.v1.to_numpy(), part.v2.to_numpy()])))
    return (pd.concat(cells) if cells else pd.Series(dtype=float)), report


def build_v1_to_2018(links: pd.DataFrame, w1: pd.Series, w2: pd.Series) -> tuple[pd.DataFrame, dict]:
    """Rows from_code, to_code, share, method, note for every v1 subclass in the correspondence."""
    rows_w = subclass_weights(w1, sorted(set(links.v1)))
    cols_w = subclass_weights(w2, sorted(set(links.v2)))
    fitted, report = ras(links, rows_w, cols_w)
    out = []
    for v1, part in links.groupby("v1"):
        targets = sorted(set(part.v2))
        note = f"2025 weights: {v1} {rows_w[v1]:.2f}; " + ", ".join(f"{t} {cols_w[t]:.2f}" for t in targets)
        if len(targets) == 1:
            shares, method = [1.0], "single link"
        elif rows_w[v1] > 0 and v1 in fitted.index.get_level_values(0):
            f = fitted.loc[v1].reindex(targets).fillna(0.0)
            shares, method = list(f / f.sum()), "RAS on 2025 weights"
            if report["misfit"][v1] > MISFIT:
                method += f" (totals conflict: new subclasses met within {report['misfit'][v1]:.0%})"
        elif cols_w[targets].sum() > 0:
            shares, method = list(cols_w[targets] / cols_w[targets].sum()), "targets' 2025 weights (source has none)"
        else:
            shares, method = [1 / len(targets)] * len(targets), "equal split (no 2025 weights)"
        for t, s in zip(targets, shares):
            if s > 0:
                out.append({"from_code": v1, "to_code": t, "share": s, "method": method, "note": note})
    table = pd.DataFrame(out)
    table["share"] = table.share / table.groupby("from_code").share.transform("sum")
    report["conflicting_sources"] = sorted(k for k, m in report.pop("misfit").items() if m > MISFIT)
    report.update({"v1_weight_total": float(rows_w.sum()), "v2_weight_total": float(cols_w.sum()),
                   "methods": table.drop_duplicates("from_code").method.value_counts().to_dict()})
    return table, report


@dataclass
class OldList:
    """One code of the 2008-2014 list: its label per year and the years it appears in."""
    code: str
    labels: dict[int, str] = field(default_factory=dict)


def _norm(label: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (label or "").lower()).strip()


def build_old_to_v1(old_codes: dict[str, OldList], v1_labels: dict[str, str], v1_spending: pd.Series) -> pd.DataFrame:
    """Rows from_code, to_code, share, method, note for every code of the 2008-2014 surveys.

    v1_spending: the bridge year's all-households spending per v1 subclass (any positive scale),
    indexed by every v1 subclass a code may go to."""
    v1_codes = sorted(v1_spending.index)
    out = []
    same = {}
    for code, entry in old_codes.items():
        labels = {_norm(l) for l in entry.labels.values() if l}
        if code in v1_spending.index and labels and _norm(v1_labels.get(code)) in labels and len(labels) == 1:
            same[code] = code
            out.append({"from_code": code, "to_code": code, "share": 1.0, "method": "same code and label",
                        "note": next(iter(entry.labels.values()))})
    taken = set(same.values())
    for code in sorted(set(old_codes) - set(same)):
        # The class (4 digits); an older 3- or 4-digit code with no subclass under it falls back to its group.
        prefix = code[:4] if len(code) >= 4 else code
        under = [c for c in v1_codes if c.startswith(prefix)]
        if not under:
            prefix = code[:3]
            under = [c for c in v1_codes if c.startswith(prefix)]
        require(under, f"no ECOICOP v1 subclass under {code[:4]} or {code[:3]} for {code}")
        free = [c for c in under if c not in taken] or under
        weight = v1_spending[free]
        label = next((l for l in old_codes[code].labels.values() if l), "")
        if weight.sum() > 0:
            shares, method = weight / weight.sum(), f"{'class' if len(prefix) == 4 else 'group'} {prefix} split by {BRIDGE_YEAR} spending"
        else:
            shares, method = pd.Series(1 / len(free), index=free), f"equal split over {prefix} (no {BRIDGE_YEAR} spending)"
        for target, s in shares.items():
            if s > 0:
                out.append({"from_code": code, "to_code": target, "share": float(s), "method": method, "note": label})
    return pd.DataFrame(out)


def build(archive, store_root: Path, out_dir: Path) -> dict:
    """Write both tables into out_dir from the archive and the store; return a report."""
    import duckdb

    from traceconomics.local import puf, v2
    from traceconomics.local.shares import leaves
    from traceconomics.sources.elstat import hbs_tables
    from traceconomics.store.query import as_of, open_views

    rec = archive.latest("eu-vocabularies", "ecoicop2-ecoicop1-correspondence")
    require(rec is not None, "no archived correspondence (eu-vocabularies/ecoicop2-ecoicop1-correspondence)")
    links = correspondence(archive.root / rec["path"])

    con = duckdb.connect()
    open_views(con, store_root)
    weights = {}
    for name, dataset, col in (("v1", "eurostat:prc_hicp_inw", "coicop"), ("v2", "eurostat:prc_hicp_iw", "coicop18")):
        df = as_of(con, dataset, where=f"geo = 'GR' AND ref_period = '{WEIGHTS_YEAR}'").df()
        df = df[df[col].str.fullmatch(r"\d{3,5}")]
        require(len(df) > 200, f"{dataset}: only {len(df)} Greek weights for {WEIGHTS_YEAR}")
        weights[name] = df.set_index(col).value
    v1_table, report = build_v1_to_2018(links, weights["v1"], weights["v2"])

    tables = v2.archived_tables(archive)
    labels = {y: hbs_tables.parse(tables[y], y).labels for y in [*OLD_LIST_YEARS, BRIDGE_YEAR]}
    old: dict[str, OldList] = {}
    for year in OLD_LIST_YEARS:
        for code in leaves(puf.read(archive, year).spending.columns):
            old.setdefault(code, OldList(code)).labels[year] = labels[year].get(code, "")
    bridge = puf.read(archive, BRIDGE_YEAR)
    w = bridge.households.weight
    spend = pd.Series({c: float((bridge.spending[c] * w).sum()) for c in leaves(bridge.spending.columns)})
    targets = sorted(set(links.v1))
    require(set(spend.index) <= set(targets), f"{BRIDGE_YEAR} codes outside the correspondence: {sorted(set(spend.index) - set(targets))[:5]}")
    old_table = build_old_to_v1(old, labels[BRIDGE_YEAR], spend.reindex(targets, fill_value=0.0))

    for year in range(BRIDGE_YEAR, 2024):
        codes = set(leaves(puf.read(archive, year).spending.columns))
        require(codes <= set(v1_table.from_code), f"{year}: codes with no COICOP 2018 mapping: {sorted(codes - set(v1_table.from_code))[:5]}")
    require(set(old_table.to_code) <= set(v1_table.from_code), "older-list targets missing from the v1 table")

    source = f"correspondence {rec['sha256'][:12]} (retrieved {rec['retrieved_at'][:10]})"
    write(v1_table, out_dir / V1_TO_2018, [
        "ECOICOP v1 subclass -> COICOP 2018 subclass: share of the source's spending. Written by `traceconomics mapping build`.",
        "Links: EU Vocabularies correspondence ECOICOP ver. 2 - ECOICOP ver. 1 (subclass level), " + source + ".",
        f"Splits: RAS fitted to Greece's {WEIGHTS_YEAR} HICP item weights, Eurostat prc_hicp_inw (v1) and prc_hicp_iw (COICOP 2018).",
        "note: the 2025 weights (per mille) of the source and its targets.",
    ])
    write(old_table, out_dir / OLD_TO_V1, [
        "Code of the 2008-2014 household budget surveys -> ECOICOP v1 subclass: share of the code's spending. Written by `traceconomics mapping build`.",
        "Same number and same label in that code's table 1.03 and in 2015's: mapped to itself. Otherwise the code's class",
        f"(its group for older 3-digit codes) is split over the remaining v1 subclasses by the {BRIDGE_YEAR} survey's all-households spending.",
        "note: the code's label in table 1.03.",
    ])
    report.update({"v1_rows": len(v1_table), "old_rows": len(old_table),
                   "old_methods": old_table.drop_duplicates("from_code").method.str.replace(r" \d+ ", " ", regex=True)
                                  .str.replace(r" \d+$", "", regex=True).value_counts().to_dict()})
    return report


def write(table: pd.DataFrame, path: Path, header: list[str]) -> None:
    with open(path, "w", encoding="utf-8", newline="") as f:
        for line in header:
            f.write(f"# {line}\n")
        w = csv.DictWriter(f, fieldnames=FIELDS, lineterminator="\n")
        w.writeheader()
        for row in table.sort_values(["from_code", "to_code"]).to_dict("records"):
            w.writerow({**row, "share": f"{row['share']:.10f}"})
