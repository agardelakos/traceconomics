"""Checks on every combination of the options, read from the written files.

Identities (strict): what must hold by construction, so a failure means an option was passed to
the wrong place, or a file was written wrongly:
  - the two tutoring options agree before 2026 (index, rates, weights used, contributions);
  - the default combination equals a saved earlier build of it (index, rates, contributions);
  - each series' division contributions add up to its annual rate;
  - every series in the files is in the availability table, and the other way round.

Reports (no pass or fail): what each option changes, for the method's explanations:
  - price source: CPI against HICP, same weights (`source`);
  - timing: the Q1-Q5 gap under rules N, F and U (`timing`);
  - imputed rent: its weight and what keeping it changes (`rent`);
  - tutoring: 2026 under both options, and each group's 2024 split (`tutoring`).
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb

DIMS = ["geo", "grouping", "group", "spending", "imputed_rent", "price_source", "weights_timing", "tutoring",
        "hh_weighting", "coicop18", "unit", "ref_period"]
CONTRIBUTION_TOLERANCE = 0.05   # pp: contributions add up to the unrounded rate; the rate is from the rounded index


def _con(folder: Path) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    for name in ("m1_index", "m1_rates", "m1_weights_used", "m1_contributions"):
        con.execute(f"CREATE VIEW {name} AS SELECT * FROM '{(Path(folder) / f'{name}.parquet').as_posix()}'")
    return con


def _dims(exclude=()):
    return ", ".join(f'"{d}"' for d in DIMS if d not in exclude)


def tutoring_identity(con) -> tuple[bool, str]:
    bad = {}
    for t in ("m1_index", "m1_rates", "m1_weights_used", "m1_contributions"):
        cols = _dims(("tutoring",)) + ", value_text"
        q = (f"SELECT {cols} FROM {t} WHERE tutoring = '{{}}' AND ref_period < '2026'")
        n = con.execute(f"SELECT count(*) FROM ({q.format('priced')} EXCEPT {q.format('excluded')})").fetchone()[0]
        m = con.execute(f"SELECT count(*) FROM ({q.format('excluded')} EXCEPT {q.format('priced')})").fetchone()[0]
        if n or m:
            bad[t] = (n, m)
    return not bad, "agree before 2026" if not bad else f"differ before 2026: {bad}"


def baseline_identity(con, baseline: Path) -> tuple[bool, str]:
    """The default combination against an earlier build of it (which may hold fewer groups)."""
    bad = {}
    for t in ("m1_index", "m1_rates", "m1_contributions"):
        old = (Path(baseline) / f"{t}.parquet").as_posix()
        cols = _dims() + ", value_text, quality"
        default = ("spending = 'purchases' AND imputed_rent = 'excluded' AND price_source = 'cpi' "
                   "AND weights_timing = 'N' AND tutoring = 'priced'")
        o = f"SELECT {cols} FROM '{old}' WHERE {default}"
        n = f"SELECT {cols} FROM {t} WHERE {default} AND (grouping, \"group\") IN (SELECT DISTINCT grouping, \"group\" FROM '{old}')"
        a = con.execute(f"SELECT count(*) FROM ({o} EXCEPT {n})").fetchone()[0]
        b = con.execute(f"SELECT count(*) FROM ({n} EXCEPT {o})").fetchone()[0]
        rows = con.execute(f"SELECT count(*) FROM ({o})").fetchone()[0]
        if a or b or not rows:
            bad[t] = (a, b, rows)
    return not bad, "equal to the earlier build" if not bad else f"differs from the earlier build: {bad}"


def contribution_identity(con) -> tuple[bool, str]:
    keys = _dims(("coicop18", "unit"))
    worst = con.execute(f"""
        WITH c AS (SELECT {keys}, sum(CAST(value AS DOUBLE)) total FROM m1_contributions
                   WHERE unit = 'PC_PNT' GROUP BY ALL),
             r AS (SELECT {keys}, CAST(value AS DOUBLE) rate FROM m1_rates WHERE unit = 'RCH_A')
        SELECT max(abs(total - rate)), count(*) FROM c JOIN r USING ({keys})
    """).fetchone()
    ok = worst[1] > 0 and worst[0] <= CONTRIBUTION_TOLERANCE
    return ok, f"{worst[1]} rates; contributions add up within {worst[0]:.4f} pp (limit {CONTRIBUTION_TOLERANCE})"


def availability_identity(con, folder: Path) -> tuple[bool, str]:
    table = json.loads((Path(folder) / "availability.json").read_text(encoding="utf-8"))
    listed = {(s["spending"], s["imputed_rent"], s["price_source"], s["weights_timing"], s["tutoring"],
               s["grouping"], s["group"]) for s in table["series"]}
    written = set(con.execute("""SELECT DISTINCT spending, imputed_rent, price_source, weights_timing, tutoring,
                                 grouping, "group" FROM m1_index""").fetchall())
    ok = listed == written
    return ok, (f"{len(written)} series, all listed" if ok else
                f"written but not listed: {sorted(written - listed)[:3]}; listed but not written: {sorted(listed - written)[:3]}")


def identities(folder: Path, baseline: Path | None = None) -> list[tuple[str, bool, str]]:
    con = _con(folder)
    out = [("tutoring options before 2026", *tutoring_identity(con)),
           ("contributions add up", *contribution_identity(con)),
           ("availability table", *availability_identity(con, folder))]
    if baseline is not None:
        out.append(("default against the earlier build", *baseline_identity(con, baseline)))
    return out


def _avg(con, where: str) -> dict:
    return {(g, int(p)): v for g, p, v in con.execute(f"""
        SELECT "group", ref_period, CAST(value AS DOUBLE) FROM m1_rates WHERE unit = 'RCH_A_AVG' AND {where}""").fetchall()}


def _gap(con, where: str) -> dict[int, float]:
    return {int(p): v for p, v in con.execute(f"""
        SELECT ref_period, CAST(value AS DOUBLE) FROM m1_rates WHERE unit = 'RCH_A_AVG_GAP' AND {where}""").fetchall()}


DEFAULT_WHERE = {"spending": "purchases", "imputed_rent": "excluded", "price_source": "cpi", "weights_timing": "N",
                 "tutoring": "priced"}


def where(**changes) -> str:
    return " AND ".join(f"{k} = '{v}'" for k, v in {**DEFAULT_WHERE, **changes}.items())


def source(folder: Path) -> dict:
    """All households and the B gap, annual averages: CPI against HICP prices, same weights."""
    con = _con(folder)
    cpi, hicp = _avg(con, where() + " AND grouping = 'all'"), _avg(con, where(price_source="hicp") + " AND grouping = 'all'")
    gc, gh = _gap(con, where() + " AND grouping = 'B'"), _gap(con, where(price_source="hicp") + " AND grouping = 'B'")
    years = sorted({y for _, y in cpi} & {y for _, y in hicp})
    return {y: {"all_cpi": cpi[("all", y)], "all_hicp": hicp[("all", y)], "gap_cpi": gc.get(y), "gap_hicp": gh.get(y)}
            for y in years}


def timing(folder: Path, grouping: str = "B") -> dict:
    con = _con(folder)
    gaps = {rule: _gap(con, where(weights_timing=rule) + f" AND grouping = '{grouping}'") for rule in ("N", "F", "U")}
    years = sorted(set().union(*gaps.values()))
    return {y: {rule: gaps[rule].get(y) for rule in gaps} for y in years}


def rent(folder: Path) -> dict:
    """Per group: the imputed-rent weight (2025, option kept) and the change in annual-average rates."""
    con = _con(folder)
    w = dict(con.execute(f"""
        SELECT grouping || '/' || "group", sum(CAST(value AS DOUBLE)) FROM m1_weights_used
        WHERE {where(imputed_rent='included')} AND ref_period = '2025' AND coicop18 LIKE '042%'
        GROUP BY 1""").fetchall())
    keep = {(f"{g}", y): v for (g, y), v in _avg(con, where(imputed_rent="included") + " AND grouping IN ('B', 'all', 'tenure', 'pensioners')").items()}
    drop = {(f"{g}", y): v for (g, y), v in _avg(con, where() + " AND grouping IN ('B', 'all', 'tenure', 'pensioners')").items()}
    groups = sorted({g for g, _ in keep})
    years = sorted({y for _, y in keep})
    names = {g: next(k for k in w if k.endswith("/" + g)) for g in groups if any(k.endswith("/" + g) for k in w)}
    return {g: {"weight_2025": w.get(names.get(g, ""), 0.0),
                "change": {y: keep[(g, y)] - drop[(g, y)] for y in years if (g, y) in keep and (g, y) in drop}}
            for g in groups}


def tutoring(folder: Path, period: str | None = None) -> dict:
    """Per group (grouping B and all households): the annual rate in the newest month under both options."""
    con = _con(folder)
    period = period or con.execute("SELECT max(ref_period) FROM m1_rates WHERE unit = 'RCH_A'").fetchone()[0]
    out = {}
    for t in ("priced", "excluded"):
        for g, v in con.execute(f"""
                SELECT grouping || '/' || "group", CAST(value AS DOUBLE) FROM m1_rates
                WHERE {where(tutoring=t)} AND unit = 'RCH_A' AND ref_period = '{period}'
                  AND grouping IN ('B', 'all')""").fetchall():
            out.setdefault(g, {})[t] = v
    edu = dict(con.execute(f"""
        SELECT grouping || '/' || "group", sum(CAST(value AS DOUBLE)) FROM m1_weights_used
        WHERE {where()} AND ref_period = '2026' AND coicop18 LIKE '10%' AND grouping IN ('B', 'all') GROUP BY 1""").fetchall())
    edu_b = dict(con.execute(f"""
        SELECT grouping || '/' || "group", sum(CAST(value AS DOUBLE)) FROM m1_weights_used
        WHERE {where(tutoring='excluded')} AND ref_period = '2026' AND coicop18 LIKE '10%' AND grouping IN ('B', 'all')
        GROUP BY 1""").fetchall())
    for g in out:
        out[g]["education_weight_priced"] = edu.get(g)
        out[g]["education_weight_excluded"] = edu_b.get(g)
    return {"period": period, "groups": out}


def detail_effect(con, archive, years=range(2015, 2020)) -> dict:
    """What pricing at class level (4 digits) instead of the finest level does to the gap, measured
    on the CPI path in years when both exist: the size of what the HICP path loses before 2015."""
    from traceconomics.module1 import index
    from traceconomics.module1.attribution import at_level
    from traceconomics.module1.weights_used import load_baskets

    blocks = index.price_blocks(con, archive)
    baskets = load_baskets(con, spending="purchases")
    out = {}
    for name, b in (("finest", baskets), ("classes", at_level(baskets, 4))):
        q1, q5 = (index.build(None, "B", q, blocks=blocks, baskets=b) for q in ("Q1", "Q5"))
        a, c = q1.annual_average_rates(), q5.annual_average_rates()
        out[name] = {y: a[y] - c[y] for y in years}
    return out


def not_by_level(con) -> dict:
    """Education not defined by level (10.5): its share of all households' purchases by survey, and
    the HICP's own 10.5 index against 10.2 where both exist (to 2014)."""
    from traceconomics.module1.prices import hicp_blocks

    shares = dict(con.execute("""
        SELECT ref_period, value FROM observations
        WHERE dataset = 'oet-local:hbs_weights' AND grouping = 'all' AND spending = 'purchases'
          AND imputed_rent = 'excluded' AND coicop18 = '105' AND measure = 'share'
        QUALIFY row_number() OVER (PARTITION BY key, ref_period ORDER BY published_at DESC, retrieved_at DESC) = 1
    """).fetchall())
    blocks = hicp_blocks(con)
    moves = {}
    for y in range(2010, 2015):
        b = blocks[y]
        moves[y] = {c: (b[c][f"{y}-12"] / b[c][f"{y - 1}-12"] - 1) * 100 for c in ("105", "1020") if c in b}
    return {"shares": {int(k): v for k, v in shares.items()}, "hicp_december_change": moves}
