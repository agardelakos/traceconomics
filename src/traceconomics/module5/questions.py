""""Same question, different sources": renters, rent paid, household income, unemployment.

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
- `gr-rent-change`, percent change on the year before: the CPI's rent index (yearly average of
  its months, each year from its own table 07 file) against the average rent renting households
  report paying, in the household budget survey and in EU-SILC. An average of what renters pay is
  not a price index (it moves with who rents what as well as with rents), and the page says so.
"""

from __future__ import annotations

from traceconomics.module5.hbs import Question, _latest


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
    silc_h = _share(_local(store_con, "oet-local:silc_tenure", "renter", "households_weighted"),
                    _local(store_con, "oet-local:silc_tenure", "all", "households_weighted"))
    hbs_h = _share(_local(store_con, "oet-local:hbs_rent", "renter", "households_weighted"),
                   _local(store_con, "oet-local:hbs_rent", "all", "households_weighted"))
    silc_p = _series(store_con, "eurostat:ilc_lvho02",
                     "geo = 'GR' AND hhcomp = 'TOTAL' AND rskpovth = 'TOTAL' AND unit = 'PC' AND tenure = 'RENT_MKT'")
    hbs_p = _share(_local(store_con, "oet-local:hbs_rent", "renter", "people_weighted"),
                   _local(store_con, "oet-local:hbs_rent", "all", "people_weighted"))
    return _question("gr-renters", "percent", [
        ({"label": "census", "source": "eurostat:cens_21hhct_r3", "reference": "eurostat-cens-21hhct-r3", "more": ["eurostat-cens-11htts-r2"],
          "definition": "households, tenants, census 2011 and 2021"}, census),
        ({"label": "silc", "source": "oet-local:silc_tenure", "reference": "elstat-silc-puf",
          "definition": "households paying rent, at market or reduced rate, EU-SILC"}, silc_h),
        ({"label": "hbs", "source": "oet-local:hbs_rent", "reference": "elstat-hbs-puf",
          "definition": "households paying rent for their main home, household budget survey"}, hbs_h),
        ({"label": "silc_persons", "source": "eurostat:ilc_lvho02", "reference": "eurostat-ilc-lvho02",
          "definition": "persons in households paying market rent, EU-SILC (Eurostat)"}, silc_p),
        ({"label": "hbs_persons", "source": "oet-local:hbs_rent", "reference": "elstat-hbs-puf",
          "definition": "persons in households paying rent, household budget survey"}, hbs_p),
    ])


def rent_paid(store_con) -> Question | None:
    return _question("gr-rent-paid", "EUR", [
        ({"label": "national_accounts", "source": "eurostat:nama_10_co3_p3", "reference": "eurostat-nama-10-co3-p3",
          "definition": "actual rentals for housing (CP041), all resident households, national accounts"},
         _series(store_con, "eurostat:nama_10_co3_p3", "geo = 'GR' AND unit = 'CP_MEUR' AND coicop = 'CP041'", 1e6)),
        ({"label": "silc", "source": "oet-local:silc_tenure", "reference": "elstat-silc-puf",
          "definition": "rent households report paying for their main home, EU-SILC, twelve months"},
         _local(store_con, "oet-local:silc_tenure", "all", "rent_paid_eur")),
        ({"label": "hbs", "source": "oet-local:hbs_rent", "reference": "elstat-hbs-puf",
          "definition": "rent paid for the main home, household budget survey"},
         _local(store_con, "oet-local:hbs_rent", "all", "rent_paid_eur")),
        ({"label": "aade", "source": "aade:pit_stats", "reference": "aade-pit-stats",
          "definition": "income from property declared on personal tax returns: all property, homes and other, as published"},
         _series(store_con, "aade:pit_stats", "geo = 'GR' AND measure = 'declared_income_property' AND unit = 'EUR'")),
    ])


def household_income(store_con) -> Question | None:
    return _question("gr-household-income", "EUR", [
        ({"label": "national_accounts", "source": "eurostat:nasa_10_nf_tr", "reference": "eurostat-nasa-10-nf-tr",
          "definition": "gross disposable income of households and the non-profits serving them (B6G), national accounts"},
         _series(store_con, "eurostat:nasa_10_nf_tr",
                 "geo = 'GR' AND unit = 'CP_MEUR' AND direct = 'RECV' AND na_item = 'B6G' AND sector = 'S14_S15'", 1e6)),
        ({"label": "aade", "source": "aade:pit_stats", "reference": "aade-pit-stats",
          "definition": "income declared on personal tax returns, before tax, as published"},
         _series(store_con, "aade:pit_stats", "geo = 'GR' AND measure = 'declared_income' AND unit = 'EUR'")),
    ])


def unemployment(store_con) -> Question | None:
    return _question("gr-unemployment", "persons", [
        ({"label": "lfs", "source": "eurostat:une_rt_a", "reference": "eurostat-une-rt-a",
          "definition": "people without work, looking and available (ILO definition), ages 15-74, labour force survey"},
         _series(store_con, "eurostat:une_rt_a", "geo = 'GR' AND age = 'Y15-74' AND unit = 'THS_PER' AND sex = 'T'", 1e3)),
        ({"label": "register", "source": "ec-empl:lmp_rjru", "reference": "ec-lmp-database",
          "definition": "registered unemployed by the employment service's own rules, annual average"},
         _series(store_con, "ec-empl:lmp_rjru",
                 "geo = 'GR' AND regis_es = 'REG_UNE' AND age = 'TOTAL' AND sex = 'T' AND unit = 'NR' AND stk_flow = 'STK'")),
    ])


def rent_weight(store_con) -> Question | None:
    nama = "geo = 'GR' AND unit = 'CP_MEUR' AND coicop = '{}'"
    return _question("gr-rent-weight", "percent", [
        ({"label": "cpi", "source": "elstat:cpi07", "reference": "elstat-cpi-items",
          "definition": "the CPI's weight for actual rent, per mille, from the year's table 07"},
         _series(store_con, "elstat:cpi07", "unit = 'PM' AND coicop18 = '041'", 0.1)),
        ({"label": "hicp", "source": "eurostat:prc_hicp_iw", "reference": "eurostat-prc-hicp-minr",
          "definition": "the HICP's weight for actual rent, per mille"},
         _series(store_con, "eurostat:prc_hicp_iw", "geo = 'GR' AND coicop18 = '041'", 0.1)),
        ({"label": "national_accounts", "source": "eurostat:nama_10_co3_p3", "reference": "eurostat-nama-10-co3-p3",
          "definition": "actual rentals over all household consumption, national accounts"},
         _share(_series(store_con, "eurostat:nama_10_co3_p3", nama.format("CP041")),
                _series(store_con, "eurostat:nama_10_co3_p3", nama.format("TOTAL")))),
        ({"label": "hbs", "source": "oet-local:hbs_weights", "reference": "elstat-hbs-puf",
          "definition": "rent's share of all households' purchases, household budget survey"},
         _series(store_con, "oet-local:hbs_weights",
                 "geo = 'GR' AND grouping = 'all' AND spending = 'purchases' AND imputed_rent = 'excluded' "
                 "AND coicop18 = '041' AND measure = 'share'", 100.0)),
    ])


def _change(series: dict[str, float]) -> dict[str, float]:
    return {p: (series[p] / series[str(int(p) - 1)] - 1) * 100 for p in sorted(series) if str(int(p) - 1) in series}


def _mean_rent(store_con, dataset: str) -> dict[str, float]:
    paid = _local(store_con, dataset, "all", "rent_paid_eur")
    renters = _local(store_con, dataset, "renter", "households_weighted")
    return {p: paid[p] / renters[p] for p in paid if renters.get(p)}


def rent_change(store_con) -> Question | None:
    from traceconomics.module1 import prices
    yearly = {}
    has_cpi = store_con.execute("SELECT count(*) FROM observations WHERE dataset = 'elstat:cpi07'").fetchone()[0]
    blocks = prices.cpi_blocks(store_con) if has_cpi else {}     # no table 07 yet: the line is left out
    for year, block in blocks.items():
        months = [v for p, v in block.get("041", {}).items() if p.startswith(f"{year}-")]
        if len(months) == 12:
            yearly[str(year)] = sum(months) / 12
    return _question("gr-rent-change", "percent", [
        ({"label": "cpi", "source": "elstat:cpi07", "reference": "elstat-cpi-items",
          "definition": "the CPI's index for actual rent, yearly average, change on the year before"}, _change(yearly)),
        ({"label": "hbs", "source": "oet-local:hbs_rent", "reference": "elstat-hbs-puf",
          "definition": "average rent renting households report paying, household budget survey, change on the year before"},
         _change(_mean_rent(store_con, "oet-local:hbs_rent"))),
        ({"label": "silc", "source": "oet-local:silc_tenure", "reference": "elstat-silc-puf",
          "definition": "average rent renting households report paying, EU-SILC, change on the year before"},
         _change(_mean_rent(store_con, "oet-local:silc_tenure"))),
    ])


def all_questions(store_con) -> list[Question]:
    found = (renters(store_con), rent_paid(store_con), rent_weight(store_con), rent_change(store_con),
             household_income(store_con), unemployment(store_con))
    return [q for q in found if q is not None]
