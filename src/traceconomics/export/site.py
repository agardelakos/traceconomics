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
from traceconomics.module1 import combinations
from traceconomics.module1.output import FLAGS, REST, TABLES

FORMAT = "v1"
OPTION_KEYS = list(combinations.OPTIONS)        # spending, imputed_rent, price_source, weights_timing, tutoring
GAP = "Q1-Q5"
SERIES_BUDGET = 150 * 1024                       # gzip bytes per setting's series file
FILE_LIMIT = 20 * 1024 * 1024                    # any one file (hosts limit files to 25 MiB)


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
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
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
    """).fetchall()
    for sp, ir, ps, wt, tu, g, q, unit, period, v in rows:
        key = (slug({"spending": sp, "imputed_rent": ir, "price_source": ps, "weights_timing": wt, "tutoring": tu}), g, q, unit)
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

    for g, q, unit, p, text in con.execute(f'SELECT grouping, "group", unit, ref_period, value_text FROM m1_index WHERE {w}').fetchall():
        e = groups.setdefault(f"{g}/{q}", {"index": arr(), "rch_a": arr(), "rch_m": arr(), "avg": {}, "se_a": arr(), "se_avg": {}})
        e["unit"] = unit
        e["index"][pos[p]] = _num(text)
    for g, q, unit, p, text in con.execute(f'SELECT grouping, "group", unit, ref_period, value_text FROM m1_rates WHERE {w}').fetchall():
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
        for unit, field in (("RCH_A", "se_a"), ("RCH_A_AVG", "se_avg"), ("RCH_A_GAP", "se_a"), ("RCH_A_AVG_GAP", "se_avg")):
            for p, v in se.get((s, g, q, unit), {}).items():
                if field == "se_a":
                    if p in pos:
                        e[field][pos[p]] = v
                else:
                    e[field][p] = v
    flag, year = FLAGS[setting["price_source"]]
    return {
        "format": FORMAT, "setting": setting, "start": axis[0], "end": axis[-1],
        "flags": [{"code": flag, "index_to": f"{year}-12", "rch_a_to": f"{year + 1}-12",
                   "rch_m_to": f"{year + 1}-01", "avg_to": str(year + 1)}],
        "groups": groups, "gaps": gaps,
        "footnotes": {f"{g}/{q}": f for (sl, g, q), f in footnotes.items() if sl == s},
    }


def contributions_file(con, setting: dict) -> dict:
    w = _where(setting)
    out: dict = {}
    for g, q, unit, code, p, text in con.execute(f"""
            SELECT grouping, "group", unit, coicop18, ref_period, value_text FROM m1_contributions
            WHERE {w} ORDER BY 1, 2, 5, 4""").fetchall():
        e = out.setdefault(f"{g}/{q}", {})
        e.setdefault(p, {})[code] = _num(text)
    return {"format": FORMAT, "setting": setting, "unit": "percentage points", "groups": out}


CSV_TABLES = ("m1_index", "m1_rates")


def downloads(con, setting: dict, folder: Path) -> list[Path]:
    folder.mkdir(parents=True, exist_ok=True)
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


def checksums(root: Path) -> Path:
    lines = []
    for path in sorted(p for p in root.rglob("*") if p.is_file() and p.name != "SHA256SUMS"):
        lines.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(root).as_posix()}")
    out = root / "SHA256SUMS"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
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


def export(store_con, archive, outputs: Path, out: Path, *, with_downloads: bool = True, log=print) -> list[Path]:
    """Write the site's data from module 1's outputs folder (`traceconomics module1 run`) and the store."""
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
    first, series_list, blocks = next(combinations.iterate(store_con, archive, only=[combinations.DEFAULT],
                                                           groups=calculator.PRESETS))
    written.append(_write_json(root / "calculator.json", calculator.build_checked(series_list, blocks["cpi"])))
    written.append(_write_json(root / "availability.json", {k: v for k, v in availability.items()
                                                           if k not in ("series", "identical")}))
    if with_downloads:
        written.append(_write_json(root / "downloads" / "availability.json", availability))
    from traceconomics.export import labels
    names = labels.build(used_codes(con), *label_sources(archive))
    written.append(_write_json(Path(out) / FORMAT / "labels" / "coicop18.json",
                               {"format": FORMAT, "sources": ["eu-vocabularies:ecoicop2-labels", "elstat:hbs-table-1.03"],
                                "labels": names}))
    shutil.copyfile(m1 / "metadata.json", root / "metadata.json")
    written.append(root / "metadata.json")
    written.append(_write_json(root / "settings.json", {"format": FORMAT, "options": combinations.OPTIONS,
                                                        "default": slug(combinations.DEFAULT), "settings": settings}))
    from traceconomics.export import bibliography
    written.append(bibliography.export(out))
    big = [p for p in root.rglob("*") if p.is_file() and p.stat().st_size > FILE_LIMIT]
    require(not big, f"files over {FILE_LIMIT} bytes: {[p.name for p in big]}")
    written.append(checksums(root))
    return written
