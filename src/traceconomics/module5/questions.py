""" "Same question, different sources": renters, rent paid, household income, unemployment.

Each question lines up every official source that answers it, each with what it counts. A
source's line is left out when its data aren't in the store yet; a question with fewer than two
lines is left out, since one source alone is not a comparison. Values are kept as the sources
give them except for the unit (millions or thousands made into units) and, for the shares, the
division that makes a share; AADE's figures are never changed (its terms forbid it), only read.

- `gr-renters`, percent: the census (households), EU-SILC (households, from the public use file;
  persons at market rent, Eurostat's table), the household budget survey (households, persons).
- `gr-rent-paid`, euros a year: the national accounts (actual rentals, CP041), EU-SILC, the
  household budget survey, and AADE's declared income from property (broader: all property).
- `gr-household-income`, euros a year: the national accounts' gross disposable income of
  households and their non-profits (B6G), and AADE's declared income on personal tax returns.
- `gr-unemployment`, persons: the labour force survey (ILO definition, ages 15-74) and the
  employment service's register (registered unemployed, annual average, DG EMPL's LMP database).
- `gr-rent-weight`, percent of spending: the CPI's and the HICP's weight for actual rent, the
  national accounts' share (CP041 over all household consumption), and the household budget
  survey's share (rent in purchases, imputed rent left out, as the CPI does).
- `gr-rent-change`, an index with 2015 = 100: the CPI's rent index (yearly average of its months,
  each year from its own table 07 file) against the average rent renting households report
  paying, in the household budget survey and in EU-SILC, each divided by its own 2015 value.
  Indices rather than yearly changes: year by year the gaps are small, while what readers ask is
  how far rents have moved over the years, and that shows only in the cumulative path. An average
  of what renters pay is not a price index (it moves with who rents what as well as with rents),
  and the page says so. No other rent series is independent of the CPI: the rent figures the
  Bank of Greece and the OECD publish are the CPI's own rent index.
"""

from __future__ import annotations

from traceconomics.module5.hbs import Question, _latest

# Every question's sources, in the order they are shown: what each line is, where it comes from
# (`source`: the store dataset; `reference`: its bibliography key, `more`: further keys), and what
# it counts. The made-up site data use the same descriptions, so a review shows the real ones.
SOURCES: dict[str, dict[str, dict]] = {
    "gr-renters": {
        "census": {
            "source": "eurostat:cens_21hhct_r3",
            "reference": "eurostat-cens-21hhct-r3",
            "more": ["eurostat-cens-11htts-r2"],
            "definition": "households, tenants, census 2011 and 2021",
        },
        "silc": {
            "source": "oet-local:silc_tenure",
            "reference": "elstat-silc-puf",
            "definition": "households paying rent, at market or reduced rate, EU-SILC",
        },
        "hbs": {
            "source": "oet-local:hbs_rent",
            "reference": "elstat-hbs-puf",
            "definition": "households paying rent for their main home, household budget survey",
        },
        "silc_persons": {
            "source": "eurostat:ilc_lvho02",
            "reference": "eurostat-ilc-lvho02",
            "definition": "persons in households paying market rent, EU-SILC (Eurostat)",
        },
        "hbs_persons": {
            "source": "oet-local:hbs_rent",
            "reference": "elstat-hbs-puf",
            "definition": "persons in households paying rent, household budget survey",
        },
    },
    "gr-rent-paid": {
        "national_accounts": {
            "source": "eurostat:nama_10_co3_p3",
            "reference": "eurostat-nama-10-co3-p3",
            "definition": "actual rentals for housing (CP041), all resident households, national accounts",
        },
        "silc": {
            "source": "oet-local:silc_tenure",
            "reference": "elstat-silc-puf",
            "definition": "rent households report paying for their main home, EU-SILC, twelve months",
        },
        "hbs": {
            "source": "oet-local:hbs_rent",
            "reference": "elstat-hbs-puf",
            "definition": "rent paid for the main home, household budget survey",
        },
        "aade": {
            "source": "aade:pit_stats",
            "reference": "aade-pit-stats",
            "definition": "income from property declared on personal tax returns: all property, homes and other, as published",
        },
    },
    "gr-household-income": {
        "national_accounts": {
            "source": "eurostat:nasa_10_nf_tr",
            "reference": "eurostat-nasa-10-nf-tr",
            "definition": "gross disposable income of households and the non-profits serving them (B6G), national accounts",
        },
        "aade": {
            "source": "aade:pit_stats",
            "reference": "aade-pit-stats",
            "definition": "income declared on personal tax returns, before tax, as published",
        },
    },
    "gr-unemployment": {
        "lfs": {
            "source": "eurostat:une_rt_a",
            "reference": "eurostat-une-rt-a",
            "definition": "people without work, looking and available (ILO definition), ages 15-74, labour force survey",
        },
        "register": {
            "source": "ec-empl:lmp_rjru",
            "reference": "ec-lmp-database",
            "definition": "registered unemployed by the employment service's own rules, annual average",
        },
    },
    "gr-rent-weight": {
        "cpi": {
            "source": "elstat:cpi07",
            "reference": "elstat-cpi-items",
            "definition": "the CPI's weight for actual rent, per mille, from the year's table 07",
        },
        "hicp": {
            "source": "eurostat:prc_hicp_iw",
            "reference": "eurostat-prc-hicp-iw",
            "definition": "the HICP's weight for actual rent, per mille",
        },
        "national_accounts": {
            "source": "eurostat:nama_10_co3_p3",
            "reference": "eurostat-nama-10-co3-p3",
            "definition": "actual rentals over all household consumption, national accounts",
        },
        "hbs": {
            "source": "oet-local:hbs_weights",
            "reference": "elstat-hbs-puf",
            "definition": "rent's share of all households' purchases, household budget survey, renters scaled to the census's share",
        },
    },
    "gr-rent-change": {
        # The Bank of Greece's and the OECD's rent figures are the CPI's own index, cited so a
        # reader sees why they aren't lines of their own.
        "cpi": {
            "source": "elstat:cpi07",
            "reference": "elstat-cpi-items",
            "more": ["bog-fsr-2023-11", "oecd-ahd-hm1-2"],
            "definition": "the CPI's index for actual rent, yearly average, 2015 = 100",
        },
        "hbs": {
            "source": "oet-local:hbs_rent",
            "reference": "elstat-hbs-puf",
            "definition": "average rent renting households report paying, household budget survey, 2015 = 100",
        },
        "silc": {
            "source": "oet-local:silc_tenure",
            "reference": "elstat-silc-puf",
            "definition": "average rent renting households report paying, EU-SILC, 2015 = 100",
        },
    },
}


def _src(qid: str, label: str) -> dict:
    return {"label": label, **SOURCES[qid][label]}


def _series(store_con, dataset: str, where: str, scale: float = 1.0) -> dict[str, float]:
    """{period: value × scale} for one series; {} when the dataset isn't in the store."""
    return {p: v * scale for p, v in _latest(store_con, dataset, "ref_period, value", f"{where} AND value IS NOT NULL")}


def _share(part: dict[str, float], whole: dict[str, float]) -> dict[str, float]:
    return {p: part[p] / whole[p] * 100 for p in sorted(part) if whole.get(p)}


def _local(store_con, dataset: str, tenure: str, measure: str) -> dict[str, float]:
    return _series(store_con, dataset, f"geo = 'GR' AND tenure = '{tenure}' AND measure = '{measure}'")


def _question(qid: str, unit: str, lines: list[tuple[dict, dict[str, float]]]) -> Question | None:
    kept = [(s, v) for s, v in lines if v]
    if len(kept) < 2:
        return None
    q = Question(qid, "gr", unit, sources=[s for s, _ in kept])
    for s, v in kept:
        q.values[s["label"]] = dict(sorted(v.items()))
    return q


def renters(store_con) -> Question | None:
    census = {}
    for ds in ("eurostat:cens_11htts_r2", "eurostat:cens_21hhct_r3"):
        rent = _series(store_con, ds, "geo = 'GR' AND hhcomp = 'TOTAL' AND unit = 'NR' AND tenure = 'RENT'")
        total = _series(store_con, ds, "geo = 'GR' AND hhcomp = 'TOTAL' AND unit = 'NR' AND tenure = 'TOTAL'")
        census.update(_share(rent, total))
    silc_h = _share(
        _local(store_con, "oet-local:silc_tenure", "renter", "households_weighted"),
        _local(store_con, "oet-local:silc_tenure", "all", "households_weighted"),
    )
    hbs_h = _share(
        _local(store_con, "oet-local:hbs_rent", "renter", "households_weighted"),
        _local(store_con, "oet-local:hbs_rent", "all", "households_weighted"),
    )
    silc_p = _series(
        store_con,
        "eurostat:ilc_lvho02",
        "geo = 'GR' AND hhcomp = 'TOTAL' AND rskpovth = 'TOTAL' AND unit = 'PC' AND tenure = 'RENT_MKT'",
    )
    hbs_p = _share(
        _local(store_con, "oet-local:hbs_rent", "renter", "people_weighted"),
        _local(store_con, "oet-local:hbs_rent", "all", "people_weighted"),
    )
    return _question(
        "gr-renters",
        "percent",
        [
            (_src("gr-renters", "census"), census),
            (_src("gr-renters", "silc"), silc_h),
            (_src("gr-renters", "hbs"), hbs_h),
            (_src("gr-renters", "silc_persons"), silc_p),
            (_src("gr-renters", "hbs_persons"), hbs_p),
        ],
    )


def rent_paid(store_con) -> Question | None:
    return _question(
        "gr-rent-paid",
        "EUR",
        [
            (
                _src("gr-rent-paid", "national_accounts"),
                _series(
                    store_con, "eurostat:nama_10_co3_p3", "geo = 'GR' AND unit = 'CP_MEUR' AND coicop = 'CP041'", 1e6
                ),
            ),
            (_src("gr-rent-paid", "silc"), _local(store_con, "oet-local:silc_tenure", "all", "rent_paid_eur")),
            (_src("gr-rent-paid", "hbs"), _local(store_con, "oet-local:hbs_rent", "all", "rent_paid_eur")),
            (
                _src("gr-rent-paid", "aade"),
                _series(
                    store_con, "aade:pit_stats", "geo = 'GR' AND measure = 'declared_income_property' AND unit = 'EUR'"
                ),
            ),
        ],
    )


def household_income(store_con) -> Question | None:
    return _question(
        "gr-household-income",
        "EUR",
        [
            (
                _src("gr-household-income", "national_accounts"),
                _series(
                    store_con,
                    "eurostat:nasa_10_nf_tr",
                    "geo = 'GR' AND unit = 'CP_MEUR' AND direct = 'RECV' AND na_item = 'B6G' AND sector = 'S14_S15'",
                    1e6,
                ),
            ),
            (
                _src("gr-household-income", "aade"),
                _series(store_con, "aade:pit_stats", "geo = 'GR' AND measure = 'declared_income' AND unit = 'EUR'"),
            ),
        ],
    )


def unemployment(store_con) -> Question | None:
    return _question(
        "gr-unemployment",
        "persons",
        [
            (
                _src("gr-unemployment", "lfs"),
                _series(
                    store_con,
                    "eurostat:une_rt_a",
                    "geo = 'GR' AND age = 'Y15-74' AND unit = 'THS_PER' AND sex = 'T'",
                    1e3,
                ),
            ),
            (
                _src("gr-unemployment", "register"),
                _series(
                    store_con,
                    "ec-empl:lmp_rjru",
                    "geo = 'GR' AND regis_es = 'REG_UNE' AND age = 'TOTAL' AND sex = 'T' AND unit = 'NR' AND stk_flow = 'STK'",
                ),
            ),
        ],
    )


def rent_weight(store_con) -> Question | None:
    nama = "geo = 'GR' AND unit = 'CP_MEUR' AND coicop = '{}'"
    return _question(
        "gr-rent-weight",
        "percent",
        [
            (
                _src("gr-rent-weight", "cpi"),
                _series(store_con, "elstat:cpi07", "unit = 'PM' AND coicop18 = '041'", 0.1),
            ),
            (
                _src("gr-rent-weight", "hicp"),
                _series(store_con, "eurostat:prc_hicp_iw", "geo = 'GR' AND coicop18 = '041'", 0.1),
            ),
            (
                _src("gr-rent-weight", "national_accounts"),
                _share(
                    _series(store_con, "eurostat:nama_10_co3_p3", nama.format("CP041")),
                    _series(store_con, "eurostat:nama_10_co3_p3", nama.format("TOTAL")),
                ),
            ),
            (
                _src("gr-rent-weight", "hbs"),
                _series(
                    store_con,
                    "oet-local:hbs_weights",
                    "geo = 'GR' AND grouping = 'all' AND spending = 'purchases' AND imputed_rent = 'excluded' "
                    "AND coicop18 = '041' AND measure = 'share'",
                    100.0,
                ),
            ),
        ],
    )


# 2015: a year all three sources hold, from which the CPI's rent index and the surveys part ways
# (until 2015 all three fell together). ELSTAT's own index is 2020 = 100 in every table 07 file,
# so the CPI line is ELSTAT's index divided by its 2015 average: the same path, another base.
BASE = "2015"


def _index(series: dict[str, float]) -> dict[str, float]:
    """Each year over the base year, × 100; {} when the base year is missing (the line is left out)."""
    base = series.get(BASE)
    return {p: series[p] / base * 100 for p in sorted(series)} if base else {}


def _mean_rent(store_con, dataset: str) -> dict[str, float]:
    paid = _local(store_con, dataset, "all", "rent_paid_eur")
    renters = _local(store_con, dataset, "renter", "households_weighted")
    return {p: paid[p] / renters[p] for p in paid if renters.get(p)}


def rent_change(store_con) -> Question | None:
    from traceconomics.module1 import prices

    yearly = {}
    has_cpi = store_con.execute("SELECT count(*) FROM observations WHERE dataset = 'elstat:cpi07'").fetchone()[0]
    blocks = prices.cpi_blocks(store_con) if has_cpi else {}  # no table 07 yet: the line is left out
    for year, block in blocks.items():
        months = [v for p, v in block.get("041", {}).items() if p.startswith(f"{year}-")]
        if len(months) == 12:
            yearly[str(year)] = sum(months) / 12
    return _question(
        "gr-rent-change",
        "index",
        [
            (_src("gr-rent-change", "cpi"), _index(yearly)),
            (_src("gr-rent-change", "hbs"), _index(_mean_rent(store_con, "oet-local:hbs_rent"))),
            (_src("gr-rent-change", "silc"), _index(_mean_rent(store_con, "oet-local:silc_tenure"))),
        ],
    )


def all_questions(store_con) -> list[Question]:
    found = (
        renters(store_con),
        rent_paid(store_con),
        rent_weight(store_con),
        rent_change(store_con),
        household_income(store_con),
        unemployment(store_con),
    )
    return [q for q in found if q is not None]
