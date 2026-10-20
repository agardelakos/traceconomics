"""Other studies' Greek series, rebuilt with their own settings (V4), to show that the differences
from ours come from choices, not from errors.

Bruegel ("Inflation inequality in the European Union and its drivers", version of 25 October
2024): for each month, a quintile's inflation is the weighted sum of its categories' year-on-year
HICP rates, with weights from Eurostat's household budget survey structure by income quintile
(hbs_str_t223, wave 2020, 3 digits, per mille, the same weights throughout), imputed rent (CP042)
left out. Categories without a 3-digit index are taken at 2 digits ("a lower level of granularity"
for some categories, e.g. CP08, in Bruegel's table 1).

Margins (tier B): monthly rates within 0.2 percentage points; annual averages 0.1 (target), 0.2
(limit). A month whose own HICP column (Bruegel's figure 1) differs from the final official
rate was built on provisional data: it is listed, not compared (September 2024, Bruegel's last
month, used the flash estimate).
"""

from __future__ import annotations

import gzip
import io
import zipfile
from dataclasses import dataclass, field

import openpyxl

from traceconomics.checks import require
from traceconomics.engine.rates import annual_rate
from traceconomics.store.query import as_of

MONTHLY_PP = 0.2
ANNUAL_TARGET_PP, ANNUAL_LIMIT_PP = 0.1, 0.2
MONTHS = {m: i for i, m in enumerate(("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"), 1)}


def hbs_structure(archive, wave: str = "2020", geo: str = "EL") -> dict[str, dict[str, float]]:
    """{quintile: {3-digit code: per mille}} from the archived hbs_str_t223."""
    rec = archive.latest("eurostat", "hbs_str_t223")
    require(rec is not None, "no archived hbs_str_t223")
    lines = gzip.decompress((archive.root / rec["path"]).read_bytes()).decode("utf-8").splitlines()
    head = [h.strip() for h in lines[0].split("\t")[1:]]
    col = head.index(wave)
    out: dict[str, dict[str, float]] = {}
    for line in lines[1:]:
        key, *cells = line.split("\t")
        _, quintile, coicop, unit, g = key.split(",")
        if g != geo or unit != "PM" or len(coicop) != 5:
            continue
        text = cells[col].strip().split(" ")[0]
        if text and text != ":":
            out.setdefault(quintile, {})[coicop[2:]] = float(text)
    return out


def bruegel_published(archive, geo: str = "EL") -> dict[str, dict[str, float]]:
    """{"QU1"|"QU5"|"TOTAL"|"HICP": {"YYYY-MM": rate}} from Bruegel's figure 1 data."""
    rec = archive.latest("bruegel", "inflation-inequality")
    require(rec is not None, "no archived Bruegel dataset")
    with zipfile.ZipFile(archive.root / rec["path"]) as z:
        data = z.read("data_figure1.xls")              # an xlsx file under an .xls name
    ws = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)[geo]
    out: dict[str, dict[str, float]] = {"QU1": {}, "QU5": {}, "TOTAL": {}, "HICP": {}}
    for row in ws.iter_rows(min_row=2, values_only=True):
        _, date, bottom, top, total, hicp = row[:6]
        if not date:
            continue
        mon, yy = str(date).split("-")
        period = f"20{yy}-{MONTHS[mon]:02d}"
        out["QU1"][period], out["QU5"][period], out["TOTAL"][period] = bottom, top, total
        out["HICP"][period] = hicp
    return out


@dataclass
class V4Result:
    name: str
    months: int = 0
    provisional: list[str] = field(default_factory=list)      # months Bruegel built on provisional data
    worst_month: tuple[str, float, float] | None = None       # period, ours, theirs
    annual: dict[int, tuple[float, float]] = field(default_factory=dict)

    @property
    def worst_month_gap(self) -> float:
        return 0.0 if self.worst_month is None else abs(self.worst_month[1] - self.worst_month[2])

    @property
    def worst_annual_gap(self) -> float:
        return max((abs(a - b) for a, b in self.annual.values()), default=0.0)

    @property
    def passed(self) -> bool:
        return self.worst_month_gap <= MONTHLY_PP + 1e-9 and self.worst_annual_gap <= ANNUAL_LIMIT_PP + 1e-9


def bruegel_rebuild(con, archive, geo: str = "GR") -> dict[str, dict[str, float]]:
    """{"QU1"|"QU5": {period: rate}}: Bruegel's method with Bruegel's inputs."""
    prices: dict[str, dict[str, float]] = {}
    for code, period, value in as_of(con, "eurostat:prc_hicp_midx", where=f"geo = '{geo}' AND unit = 'I15'") \
            .project("coicop, ref_period, value").fetchall():
        if value is not None and code.isdigit() and len(code) in (2, 3):
            prices.setdefault(code, {})[period] = value
    out = {}
    for quintile, shares in hbs_structure(archive).items():
        if quintile not in ("QU1", "QU5"):
            continue
        weights: dict[str, float] = {}
        for code, w in shares.items():
            if code.startswith("042") or not w:
                continue
            target = code if code in prices else code[:2]
            if target in prices:
                weights[target] = weights.get(target, 0.0) + w
        total = sum(weights.values())
        rates = {}
        for period in sorted(prices["01"]):
            parts = [(w, annual_rate(prices[c], period)) for c, w in weights.items()]
            if all(r is not None for _, r in parts):
                rates[period] = sum(w * r for w, r in parts) / total
        out[quintile] = rates
    return out


def v4_bruegel(con, archive, geo: str = "GR") -> list[V4Result]:
    ours = bruegel_rebuild(con, archive)
    theirs = bruegel_published(archive)
    official = {p: v for p, v in as_of(con, "eurostat:prc_hicp_midx", where=f"geo = '{geo}' AND unit = 'I15' "
                                       "AND coicop = 'TOTAL'").project("ref_period, value").fetchall()}
    provisional = sorted(p for p, v in theirs["HICP"].items()
                         if annual_rate(official, p) is None or abs(annual_rate(official, p) - v) > 0.005)
    results = []
    for q in ("QU1", "QU5"):
        r = V4Result(f"Bruegel {q}", provisional=provisional)
        common = sorted(set(ours[q]) & set(theirs[q]) - set(provisional))
        for p in common:
            a, b = ours[q][p], theirs[q][p]
            r.months += 1
            if r.worst_month is None or abs(a - b) > r.worst_month_gap:
                r.worst_month = (p, a, b)
        for y in sorted({int(p[:4]) for p in common}):
            ps = [p for p in common if p.startswith(str(y))]
            if len(ps) == 12:
                r.annual[y] = (sum(ours[q][p] for p in ps) / 12, sum(theirs[q][p] for p in ps) / 12)
        results.append(r)
    return results


# -- KEPE ----------------------------------------------------------------------------------------

def kepe_published() -> dict:
    import tomllib
    from importlib import resources
    data = tomllib.loads(resources.files("traceconomics.data").joinpath("benchmarks_gr.toml").read_text(encoding="utf-8"))
    return data["kepe-2025"]


def kepe_rule(years, surveys, release_dates=None):
    """KEPE's timing: the same year's survey for 2016-2022, ELSTAT's rule (survey y-2) after."""
    from traceconomics.module1.schedule import FINAL, Entry
    out = []
    for y in years:
        h = y if y <= 2022 else y - 2
        if h not in surveys:
            break
        out.append(Entry(y, h, FINAL, f"{y}-01", "KEPE's timing"))
    return out


def divisions_only(baskets: dict) -> dict:
    """The same baskets cut to the 2-digit divisions (KEPE prices the 12 divisions)."""
    from traceconomics.module1.weights_used import Basket
    return {k: Basket({c: s for c, s in b.shares.items() if len(c) == 2},
                      {c: r for c, r in b.reliability.items() if len(c) == 2}) for k, b in baskets.items()}


def v4_kepe(con) -> dict:
    """KEPE's settings, with the two it doesn't state tested both ways (people or households;
    purchases or all spending). Returns, per variant, our P20/R20/R10 annual averages for
    2021-2024 and the gaps to KEPE's chart (tier B on one-decimal published figures)."""
    from traceconomics.module1 import index
    from traceconomics.module1.weights_used import load_baskets

    pub = kepe_published()["chart1"]
    blocks = index.cpi_blocks(con)
    variants = {}
    for spending in ("purchases", "all"):
        baskets = divisions_only(load_baskets(con, spending=spending))
        for ranking, (q, d) in {"people": ("B", "B10"), "households": ("BH", "BH10")}.items():
            rates = {}
            for name, (g, label) in {"P20": (q, "Q1"), "R20": (q, "Q5"), "R10": (d, "D10")}.items():
                s = index.build(None, g, label, spending=spending, blocks=blocks, baskets=baskets,
                                rule=kepe_rule, first_year=2016)
                rates[name] = {y: round(v, 2) for y, v in s.annual_average_rates().items() if 2021 <= y <= 2024}
            gaps = [abs(rates[k][int(y)] - v) for k in ("P20", "R20", "R10") for y, v in pub[k].items()
                    if int(y) in rates[k]]
            variants[(spending, ranking)] = {"rates": rates, "max_gap": max(gaps), "mean_gap": sum(gaps) / len(gaps)}
    return variants
