"""The website's data files, from module 1's outputs: small, per option setting, ready to fetch.

    <out>/v1/gr/m1/latest/
        series/<setting>.json        every group's index, rates, error bands and the Q1-Q5 gaps
        contributions/<setting>.json each division's contribution to each group's annual rate
        calculator.json              the personal calculator's inputs (`calculator`)
        downloads/<setting>/<table>.{parquet,csv}
                                     Parquet for every table; CSV for the index and the rates,
                                     and for every table of the default setting (all of it as
                                     CSV would be about 1 GB: the full set is a release file)
        availability.json            which periods each option covers, what is greyed out, and why
                                     (the per-series detail is in each series file's footnotes, and
                                     in full in downloads/availability.json)
        metadata.json                dimensions, units, sources, licence, input manifest
        settings.json                the settings, their file names and labels' keys
        official.json                the official CPI's latest annual rate, the context the site
                                     shows next to the groups' rates: ours from ELSTAT's index
                                     levels and ELSTAT's published one, compared (`official_rate`)
        income-limits.json           each income fifth's upper limit in euros, ours (from the household
                                     budget survey) and Eurostat's (EU-SILC), with years, standard
                                     errors and PPS (`income_limits_file`)
        household-types.json         each household type's share of households, newest survey year
        SHA256SUMS                   a checksum for every file above
    <out>/v1/labels/coicop18.json    the spending categories' names in English and Greek (`labels`)
    <out>/v1/references.json         the bibliography, for the site's source lists (`bibliography`)

A <setting> is `<spending>_<imputed rent>_<price source>_<weights timing>_<tutoring>`, e.g.
`purchases_excluded_cpi_N_priced` (the default). Values are the published, rounded ones
(`value_text`): what a reader sees is what a download holds.

Series arrays run over one month axis per file (`start` to `end`), with null where a value
doesn't exist. Only aggregates are written: nothing here comes from a single household.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path

import duckdb

from traceconomics.checks import require
from traceconomics.engine import rates
from traceconomics.module1 import combinations, prices
from traceconomics.module1.output import FLAGS, REST, TABLES
from traceconomics.sources.elstat.parse import TOTAL

FORMAT = "v1"
OPTION_KEYS = list(combinations.OPTIONS)  # spending, imputed_rent, price_source, weights_timing, tutoring
GAP = "Q1-Q5"
SERIES_BUDGET = 150 * 1024  # gzip bytes per setting's series file
FILE_LIMIT = 20 * 1024 * 1024  # any one file (hosts limit files to 25 MiB)
PUBLISHED_RATE = "elstat:cpi05"  # ELSTAT's own twelve-month rates (table 05)


def slug(setting: dict) -> str:
    return "_".join(setting[k] for k in OPTION_KEYS)


def _months(start: str, end: str) -> list[str]:
    y, m = int(start[:4]), int(start[5:7])
    out = []
    while f"{y}-{m:02d}" <= end:
        out.append(f"{y}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def _num(text: str | None):
    return None if text in (None, "") else float(text)


def _write_json(path: Path, data) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8", newline="\n")
    return path


def _where(setting: dict) -> str:
    return " AND ".join(f"{k} = '{setting[k]}'" for k in OPTION_KEYS)


def bands(store_con) -> dict:
    """{(setting slug, grouping, group, unit): {period: se}} from the newest error-band file."""
    out: dict = {}
    rows = store_con.execute("""
        SELECT spending, imputed_rent, price_source, weights_timing, tutoring, grouping, "group", unit, ref_period, value
        FROM observations WHERE dataset = 'oet-local:hbs_bands' AND measure = 'se'
        QUALIFY row_number() OVER (PARTITION BY key, ref_period ORDER BY published_at DESC, retrieved_at DESC) = 1
            AND status <> 'withdrawn'
        ORDER BY spending, imputed_rent, price_source, weights_timing, tutoring, grouping, "group", unit, ref_period
    """).fetchall()
    # The window above returns rows in any order; the fixed order makes the files byte-identical
    # from run to run and machine to machine.
    for sp, ir, ps, wt, tu, g, q, unit, period, v in rows:
        key = (
            slug({"spending": sp, "imputed_rent": ir, "price_source": ps, "weights_timing": wt, "tutoring": tu}),
            g,
            q,
            unit,
        )
        out.setdefault(key, {})[period] = round(v, 3)
    return out


def series_file(con, setting: dict, se: dict, footnotes: dict) -> dict:
    w = _where(setting)
    s = slug(setting)
    rng = con.execute(f"SELECT min(ref_period), max(ref_period) FROM m1_index WHERE {w}").fetchone()
    axis = _months(*rng)
    pos = {p: i for i, p in enumerate(axis)}
    groups: dict = {}
    gaps: dict = {}

    def arr():
        return [None] * len(axis)

    for g, q, unit, p, text in con.execute(
        f'SELECT grouping, "group", unit, ref_period, value_text FROM m1_index WHERE {w}'
    ).fetchall():
        e = groups.setdefault(
            f"{g}/{q}", {"index": arr(), "rch_a": arr(), "rch_m": arr(), "avg": {}, "se_a": arr(), "se_avg": {}}
        )
        e["unit"] = unit
        e["index"][pos[p]] = _num(text)
    for g, q, unit, p, text in con.execute(
        f'SELECT grouping, "group", unit, ref_period, value_text FROM m1_rates WHERE {w}'
    ).fetchall():
        if q == GAP:
            e = gaps.setdefault(g, {"rch_a": arr(), "avg": {}, "se_a": arr(), "se_avg": {}})
            if unit == "RCH_A_GAP":
                e["rch_a"][pos[p]] = _num(text)
            elif unit == "RCH_A_AVG_GAP":
                e["avg"][p] = _num(text)
            continue
        e = groups[f"{g}/{q}"]
        if unit in ("RCH_A", "RCH_M"):
            e[unit.lower()][pos[p]] = _num(text)
        elif unit == "RCH_A_AVG":
            e["avg"][p] = _num(text)
    for key, e in list(groups.items()) + [(f"{g}/{GAP}", e) for g, e in gaps.items()]:
        g, q = key.split("/")
        for unit, field in (
            ("RCH_A", "se_a"),
            ("RCH_A_AVG", "se_avg"),
            ("RCH_A_GAP", "se_a"),
            ("RCH_A_AVG_GAP", "se_avg"),
        ):
            for p, v in se.get((s, g, q, unit), {}).items():
                if field == "se_a":
                    if p in pos:
                        e[field][pos[p]] = v
                else:
                    e[field][p] = v
    flag, year = FLAGS[setting["price_source"]]
    return {
        "format": FORMAT,
        "setting": setting,
        "start": axis[0],
        "end": axis[-1],
        "flags": [
            {
                "code": flag,
                "index_to": f"{year}-12",
                "rch_a_to": f"{year + 1}-12",
                "rch_m_to": f"{year + 1}-01",
                "avg_to": str(year + 1),
            }
        ],
        "groups": groups,
        "gaps": gaps,
        "footnotes": {f"{g}/{q}": f for (sl, g, q), f in footnotes.items() if sl == s},
    }


def contributions_file(con, setting: dict) -> dict:
    w = _where(setting)
    out: dict = {}
    for g, q, _unit, code, p, text in con.execute(f"""
            SELECT grouping, "group", unit, coicop18, ref_period, value_text FROM m1_contributions
            WHERE {w} ORDER BY 1, 2, 5, 4""").fetchall():
        e = out.setdefault(f"{g}/{q}", {})
        e.setdefault(p, {})[code] = _num(text)
    return {"format": FORMAT, "setting": setting, "unit": "percentage points", "groups": out}


CSV_TABLES = ("m1_index", "m1_rates")


def downloads(con, setting: dict, folder: Path) -> list[Path]:
    folder.mkdir(parents=True, exist_ok=True)
    # One thread while writing: with several, the Parquet row groups depend on the number of cores,
    # and the same rows would give different files on different machines.
    con.execute("SET threads = 1")
    written = []
    for table in TABLES:
        q = f"SELECT * FROM {table} WHERE {_where(setting)}"
        formats = [("parquet", "(FORMAT parquet, COMPRESSION zstd)")]
        if table in CSV_TABLES or setting == combinations.DEFAULT:
            formats.append(("csv", "(HEADER, DELIMITER ',')"))
        for ext, opts in formats:
            path = folder / f"{table}.{ext}"
            con.execute(f"COPY ({q}) TO '{path.as_posix()}' {opts}")
            written.append(path)
    return written


# Our rate and ELSTAT's published one agree when they differ by no more than floating-point noise:
# both come from the same index levels, so any larger gap means something changed on one side.
AGREE = 1e-9  # percentage points


def official_rate(blocks: dict, published: dict[str, float]) -> dict:
    """The official CPI's annual rate in its latest month: ours, and ELSTAT's published one.

    Ours is computed from ELSTAT's overall index in table 07, not copied, like every rate on the
    site: the month over the same month a year before, each level from its own year's file (the
    overall index is one published series, so the files' levels are on the same base), at full
    precision, as ELSTAT computes it. ELSTAT's own rate is from table 05 (`published`: "YYYY-MM"
    -> rate as a fraction, as the file holds it). Each carries its own month; where they share
    one, the file says whether they agree. A disagreement is published, never hidden: it is a
    finding to explain.
    """
    year = max(blocks)
    total = {
        p: v for y in (year - 1, year) for p, v in blocks.get(y, {}).get(TOTAL, {}).items() if p.startswith(f"{y}-")
    }
    latest = max(p for p in total if p.startswith(f"{year}-"))
    ours = rates.annual_rate(total, latest)
    require(ours is not None, f"no overall CPI index a year before {latest}")
    require(bool(published), "no published rate from ELSTAT's table 05")
    theirs_period = max(published)
    theirs = published[theirs_period] * 100
    out = {
        "format": FORMAT,
        "series": "CPI, all items",
        "unit": "percent",
        "computed": {
            "source": prices.DATASET,
            "reference": "elstat-cpi-items",
            "period": latest,
            "annual_rate": float(f"{ours:.1f}"),
            "annual_rate_full": ours,
        },
        "published": {
            "source": PUBLISHED_RATE,
            "reference": "elstat-cpi-rates",
            "period": theirs_period,
            "annual_rate": float(f"{theirs:.1f}"),
            "annual_rate_full": theirs,
        },
    }
    if theirs_period == latest:
        gap = ours - theirs
        out["comparison"] = {"period": latest, "difference": gap, "agree": abs(gap) <= AGREE}
    return out


def published_rates(store_con) -> dict[str, float]:
    """ELSTAT's twelve-month rates of the overall CPI (table 05), as published: "YYYY-MM" -> fraction."""
    rows = store_con.execute(
        """
        SELECT ref_period, value FROM observations
        WHERE dataset = $d AND freq = 'M' AND unit = 'RCH_A_FR'
        QUALIFY row_number() OVER (PARTITION BY key, ref_period ORDER BY published_at DESC, retrieved_at DESC) = 1
            AND status <> 'withdrawn'
        ORDER BY ref_period
    """,
        {"d": PUBLISHED_RATE},
    ).fetchall()
    return {p: v for p, v in rows if v is not None}


def official_file(store_con) -> dict:
    """`official_rate` on the CPI in the store."""
    return official_rate(prices.cpi_blocks(store_con), published_rates(store_con))


def _latest(store_con, dataset: str, columns: str, where: str = "TRUE") -> list[tuple]:
    """The newest value of each key and period of `dataset`, withdrawn rows left out, in a fixed order."""
    return store_con.execute(
        f"""
        SELECT {columns} FROM observations WHERE dataset = $d AND {where}
        QUALIFY row_number() OVER (PARTITION BY key, ref_period ORDER BY published_at DESC, retrieved_at DESC) = 1
            AND status <> 'withdrawn'
        ORDER BY {columns}
    """,
        {"d": dataset},
    ).fetchall()


def pps_factor(eur: dict[str, float], pps: dict[str, float]) -> float:
    """Euros per purchasing power standard, from one year of Eurostat's limits in both units: the
    total in euros over the total in PPS (the least affected by their rounding to whole units).
    Eurostat converts every limit of a year with one factor; a limit that doesn't fit it within
    a euro means the file changed meaning, and is refused."""
    require(eur.keys() == pps.keys() and eur, f"limits in EUR {sorted(eur)} and PPS {sorted(pps)} don't match")
    factor = sum(eur.values()) / sum(pps.values())
    off = {k: eur[k] - factor * pps[k] for k in eur if abs(eur[k] - factor * pps[k]) > 1}
    require(not off, f"Eurostat's PPS limits don't share one factor: {off}")
    return factor


def income_limits_file(store_con) -> dict:
    """Each income fifth's upper limit, ours and Eurostat's, for the site's Groups page.

    Ours: the household budget survey's limits (`hbs_limits`) for its newest year, with standard
    errors and each fifth's household count; every year's limits too, for the record. Eurostat's
    (EU-SILC, `ilc_di01`, top cut-offs): the survey that describes the same year's incomes (SILC
    survey y + 1 for our survey y), or its newest one when that isn't out yet. Ours in purchasing
    power standards use the factor Eurostat applies to that income year (`pps_factor`), or are
    null with a reason when Eurostat hasn't published it yet."""
    ours: dict[int, dict] = {}
    for year, group, measure, text, value in _latest(
        store_con,
        "oet-local:hbs_limits",
        'ref_period, "group", measure, value_text, value',
        "grouping = 'B' AND geo = 'GR'",
    ):
        ours.setdefault(int(year), {}).setdefault(measure, {})[group] = value if measure != "se_design" else text
    require(ours, "no income limits in the store (oet-local:hbs_limits): run `traceconomics weights run`")
    counts: dict[int, dict] = {}
    for year, group, text in _latest(
        store_con,
        "oet-local:hbs_groups",
        'ref_period, "group", value_text',
        "grouping = 'B' AND geo = 'GR' AND measure = 'n_households'",
    ):
        counts.setdefault(int(year), {})[group] = text
    # Checked before the query below: the store's view only has ilc_di01's columns (quant_inc,
    # statinfo) once some of its rows are in, so without them that query fails on a column name.
    missing_silc = (
        "no Eurostat income limits in the store (eurostat:ilc_di01): the job fetches them "
        "on a due run, or now with `traceconomics archive --force`"
    )
    require(
        store_con.execute("SELECT count(*) FROM observations WHERE dataset = 'eurostat:ilc_di01'").fetchone()[0],
        missing_silc,
    )
    silc: dict[int, dict] = {}
    for year, quant, unit, value in _latest(
        store_con,
        "eurostat:ilc_di01",
        "ref_period, quant_inc, unit, value",
        "geo = 'GR' AND statinfo = 'TC' AND unit IN ('EUR', 'PPS') "
        "AND quant_inc IN ('QU1', 'QU2', 'QU3', 'QU4') AND value IS NOT NULL",
    ):
        silc.setdefault(int(year), {}).setdefault(unit, {})["Q" + quant[-1]] = value
    silc = {y: v for y, v in silc.items() if len(v.get("EUR", {})) == 4 and len(v.get("PPS", {})) == 4}
    require(silc, missing_silc)

    def whole(x):
        return None if x is None else int(round(x))

    newest = max(ours)
    mine = ours[newest]
    matching = newest + 1
    eurostat_year = matching if matching in silc else max(silc)
    factor = pps_factor(silc[matching]["EUR"], silc[matching]["PPS"]) if matching in silc else None
    groups = sorted(mine["limit"])
    return {
        "format": FORMAT,
        "ours": {
            "source": "oet-local:hbs_limits",
            "survey_year": newest,
            "income_year": newest,
            "unit": "EUR a year per adult equivalent: money income after taxes over the modified OECD scale",
            "method": "midpoint between the two households either side of each limit, rounded to the euro",
            "top_cutoffs": {g: whole(mine["limit"][g]) for g in groups},
            "se": {g: whole(mine.get("se", {}).get(g)) for g in groups},
            "se_design": mine.get("se_design", {}).get(groups[0]),
            "households": {g: counts.get(newest, {}).get(g) for g in [*groups, f"Q{len(groups) + 1}"]},
            "top_cutoffs_pps": {g: whole(mine["limit"][g] / factor) for g in groups} if factor else None,
            "pps_factor": round(factor, 6) if factor else None,
            "pps_reason": None if factor else "no_factor",
            "years": {str(y): {g: whole(v) for g, v in sorted(ours[y]["limit"].items())} for y in sorted(ours)},
        },
        "eurostat": {
            "source": "eurostat:ilc_di01",
            "survey_year": eurostat_year,
            "income_year": eurostat_year - 1,
            "unit": "EUR a year per adult equivalent: disposable income over the modified OECD scale",
            "top_cutoffs": {g: whole(v) for g, v in sorted(silc[eurostat_year]["EUR"].items())},
            "top_cutoffs_pps": {g: whole(v) for g, v in sorted(silc[eurostat_year]["PPS"].items())},
        },
    }


def household_types_file(store_con) -> dict:
    """Each household type's share of households and its surveyed households, for the newest survey
    year, for the Groups page (from the archived groups tables, `hbs_groups`)."""
    rows = _latest(
        store_con,
        "oet-local:hbs_groups",
        'ref_period, grouping, "group", measure, value_text, value',
        "geo = 'GR' AND grouping IN ('hhtype', 'all') AND measure IN ('households_weighted', 'n_households')",
    )
    by_year: dict[int, dict] = {}
    for year, grouping, group, measure, text, value in rows:
        by_year.setdefault(int(year), {}).setdefault(f"{grouping}/{group}", {})[measure] = (value, text)
    years = [y for y, g in by_year.items() if "all/all" in g and any(k.startswith("hhtype/") for k in g)]
    require(years, "no household-type groups in the store (oet-local:hbs_groups): run `traceconomics weights run`")
    year = max(years)
    groups = by_year[year]
    total = groups["all/all"]["households_weighted"][0]
    return {
        "format": FORMAT,
        "source": "oet-local:hbs_groups",
        "survey_year": year,
        "groups": {
            k: {"share": round(v["households_weighted"][0] / total, 4), "households": v["n_households"][1]}
            for k, v in sorted(groups.items())
            if k.startswith("hhtype/")
        },
    }


def checksums(root: Path) -> Path:
    lines = []
    for path in sorted(p for p in root.rglob("*") if p.is_file() and p.name != "SHA256SUMS"):
        lines.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(root).as_posix()}")
    out = root / "SHA256SUMS"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return out


TABLE_103 = re.compile(r"SFA05_TB_AN_00_(\d{4})_103_F_(EN|GR)\.xlsx$")


def label_sources(archive) -> tuple[Path, Path, Path]:
    """(EU Vocabularies labels, newest HBS table 1.03 in English, the same year in Greek)."""
    rec = archive.latest("eu-vocabularies", "ecoicop2-labels")
    require(rec is not None, "the archive holds no eu-vocabularies/ecoicop2-labels")
    found: dict[int, dict[str, Path]] = {}
    for source, dataset in archive.datasets():
        if source != "elstat" or not dataset.startswith("doc-"):
            continue
        r = archive.latest(source, dataset)
        m = TABLE_103.search(archive.manifest(r).get("original_name") or "")
        if m:
            found.setdefault(int(m.group(1)), {})[m.group(2)] = archive.root / r["path"]
    years = [y for y, f in found.items() if {"EN", "GR"} <= set(f)]
    require(years, "the archive holds no household budget survey table 1.03 in both English and Greek")
    newest = found[max(years)]
    return archive.root / rec["path"], newest["EN"], newest["GR"]


def used_codes(con) -> set[str]:
    """Every category code the site's files name: weights (a rest row names its parent), the
    indices that price them, contributions."""
    codes = set()
    for (c,) in con.execute("SELECT DISTINCT coicop18 FROM m1_weights_used").fetchall():
        codes.add(c[: -len(REST)] if c.endswith(REST) else c)
    for (p,) in con.execute("SELECT DISTINCT priced_with FROM m1_weights_used").fetchall():
        codes.update(p.split("+"))
    for (c,) in con.execute("SELECT DISTINCT coicop18 FROM m1_contributions").fetchall():
        codes.add(c)
    return {c for c in codes if c and c != "TOTAL"}


def export(
    store_con, archive, outputs: Path, out: Path, *, with_downloads: bool = True, log=print, blocks=None, baskets=None
) -> list[Path]:
    """Write the site's data from module 1's outputs folder (`traceconomics module1 run`) and the store.
    `blocks` and `baskets`: the calculator's inputs, as `combinations.iterate` takes them (default:
    loaded from the store and archive)."""
    import gzip

    from traceconomics.export import calculator

    m1 = Path(outputs) / "gr" / "m1"
    root = Path(out) / FORMAT / "gr" / "m1" / "latest"
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    con = duckdb.connect()
    for table in TABLES:
        con.execute(f"CREATE VIEW {table} AS SELECT * FROM '{(m1 / f'{table}.parquet').as_posix()}'")
    availability = json.loads((m1 / "availability.json").read_text(encoding="utf-8"))
    footnotes = {(slug(r), r["grouping"], r["group"]): r["footnotes"] for r in availability["series"] if r["footnotes"]}
    se = bands(store_con)
    written = []
    settings = []
    for setting in combinations.settings():
        s = slug(setting)
        series = series_file(con, setting, se, footnotes)
        path = _write_json(root / "series" / f"{s}.json", series)
        size = len(gzip.compress(path.read_bytes(), 9))
        require(size <= SERIES_BUDGET, f"{path.name}: {size} bytes compressed, over the budget of {SERIES_BUDGET}")
        written += [path, _write_json(root / "contributions" / f"{s}.json", contributions_file(con, setting))]
        if with_downloads:
            written += downloads(con, setting, root / "downloads" / s)
        settings.append({**setting, "slug": s, "default": setting == combinations.DEFAULT})
        log(f"{s}: series {size // 1024} KB compressed")
    first, series_list, used = next(
        combinations.iterate(
            store_con, archive, only=[combinations.DEFAULT], groups=calculator.PRESETS, blocks=blocks, baskets=baskets
        )
    )
    written.append(_write_json(root / "calculator.json", calculator.build_checked(series_list, used["cpi"])))
    written.append(
        _write_json(
            root / "availability.json", {k: v for k, v in availability.items() if k not in ("series", "identical")}
        )
    )
    if with_downloads:
        written.append(_write_json(root / "downloads" / "availability.json", availability))
    from traceconomics.export import labels

    names = labels.build(used_codes(con), *label_sources(archive))
    written.append(
        _write_json(
            Path(out) / FORMAT / "labels" / "coicop18.json",
            {
                "format": FORMAT,
                "sources": ["eu-vocabularies:ecoicop2-labels", "elstat:hbs-table-1.03"],
                "labels": names,
            },
        )
    )
    shutil.copyfile(m1 / "metadata.json", root / "metadata.json")
    written.append(root / "metadata.json")
    written.append(_write_json(root / "official.json", official_file(store_con)))
    written.append(_write_json(root / "income-limits.json", income_limits_file(store_con)))
    written.append(_write_json(root / "household-types.json", household_types_file(store_con)))
    written.append(
        _write_json(
            root / "settings.json",
            {
                "format": FORMAT,
                "options": combinations.OPTIONS,
                "default": slug(combinations.DEFAULT),
                "settings": settings,
            },
        )
    )
    from traceconomics.export import bibliography

    written.append(bibliography.export(out))
    big = [p for p in root.rglob("*") if p.is_file() and p.stat().st_size > FILE_LIMIT]
    require(not big, f"files over {FILE_LIMIT} bytes: {[p.name for p in big]}")
    written.append(checksums(root))
    written += export_m5(outputs, out, log)
    return written


def export_m5(outputs: Path, out: Path, log=print) -> list[Path]:
    """Copy the consistency checks (`traceconomics module5 run`) to the site's data, as written:
    `checks.json` for the pages, each check's and question's CSV under `downloads/`. Left out,
    with a line in the log, when the outputs folder has no `m5` (the topic has no pages then)."""
    written = []
    for folder in sorted(Path(outputs).glob("*/m5")):
        country = folder.parent.name
        root = Path(out) / FORMAT / country / "m5" / "latest"
        if root.exists():
            shutil.rmtree(root)
        (root / "downloads").mkdir(parents=True)
        doc = json.loads((folder / "checks.json").read_text(encoding="utf-8"))
        require(
            doc.get("format") == "m5-v1" and doc.get("country") == country,
            f"{folder / 'checks.json'}: not module5's results for {country}",
        )
        shutil.copyfile(folder / "checks.json", root / "checks.json")
        written.append(root / "checks.json")
        for csv_path in sorted(folder.glob("*.csv")):
            shutil.copyfile(csv_path, root / "downloads" / csv_path.name)
            written.append(root / "downloads" / csv_path.name)
        big = [p for p in root.rglob("*") if p.is_file() and p.stat().st_size > FILE_LIMIT]
        require(not big, f"files over {FILE_LIMIT} bytes: {[p.name for p in big]}")
        written.append(checksums(root))
        log(f"{country}/m5: {len(doc['checks'])} checks, {len(doc.get('questions', []))} questions")
    if not written:
        log("no module5 results in the outputs folder: the consistency topic's files are left out")
    return written
