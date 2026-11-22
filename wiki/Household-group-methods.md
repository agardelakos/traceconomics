# Household group methods

How each household group gets its own basket of weights from the household budget survey, how
those weights become an index, and how uncertain they are. This page is for contributors and
reviewers: what is computed, where, and what tests it. The economics, and the reasons for each
default, are on the site's method pages
([inflation by household](https://traceconomics.com/en/gr/inflation-by-group/method/)).

The survey's public use files are microdata: they are read only by `src/traceconomics/local/`, in
memory, on the maintainer's own machines, and never reach the repository, a test or a published
file. What leaves that code is aggregates (spending shares by group, income limits, standard
errors), archived as the project's own dataset. Tests use small synthetic surveys built in the
test.

## The pipeline, in one line per step

1. **Map** each survey's spending codes to COICOP 2018 (`local/mapping.py`).
2. **Calibrate** each survey's household weights to the census's tenure split
   (`local/calibration.py`).
3. **Group** the households (`local/groups.py`).
4. **Share**: each group's spending on each item over its total (`local/shares.py`), with
   bootstrap standard errors (`local/bootstrap.py`).
5. **Time** the weights: which survey each index year uses (`module1/schedule.py`).
6. **Price and price-update** the shares (`module1/weights_used.py`), then **chain** at December
   with the engine ([Price index methods](Price-index-methods)).
7. **Bands**: the same steps on every bootstrap replicate (`local/bands.py`).

Steps 1 to 4 run once per survey year (`traceconomics weights run`) and are archived; steps 5 to 7
run in every release build.

## Mapping old survey codes to COICOP 2018

The price indices use COICOP 2018 from 2026, and the survey from 2024. Older surveys use two older
lists, and codes are never matched by number alone: `01112` is "bread" up to 2014 and "flours and
other cereals" from 2015.

- **2015 to 2023, ECOICOP version 1 → COICOP 2018** (`data/coicop_v1_2018.csv`), along the links of
  the official correspondence. Where a v1 subclass has several targets, its spending is split by
  iterative proportional fitting (RAS): the v1 x 2018 table, zero outside the correspondence's
  links, is scaled until its rows match Greece's 2025 HICP item weights in v1 and its columns the
  same year's weights in COICOP 2018. Both describe the same spending, so the fitted table is the
  split the two classifications agree on.
- **2008 to 2014, the national list → ECOICOP v1** (`data/hbs_2008_2014_v1.csv`). A code with the
  same number and label in both lists maps to itself; the rest of a class is pooled and split over
  its remaining v1 subclasses by the 2015 survey's spending.

The mapping is applied household by household, so totals are kept and every grouping works on the
result. `traceconomics check mapping` checks the tables; tests PY-MAP-001 to 018.

## Calibrating to the census's renters

The survey finds about a third fewer renting households than the census (16.8% against 24.5% in
2021), in every region and household type, and its weights are never adjusted for tenure. With
renters missing, rent weighs too little in every group that mixes tenures.

So before any group is formed, each survey's weights are scaled by one factor per tenure class
(renters, owners, housed free) to match a target split, with the number of households unchanged:
post-stratification on one margin. The target is EU-SILC's household split, which EU-SILC fits to
the census. EU-SILC moved from the 2011 to the 2021 census in one step (21.8% to 24.5% renters in
one year); the target spreads that step over the ten years between the censuses, a tenth a year.

- Scaling every renter by the same factor leaves each tenure's own basket as it was: only the
  groups that mix tenures change, and which fifth some households fall in.
- The comparisons with ELSTAT's own tables keep the survey's weights as published: they check our
  reading of the file, not our method.
- Each bootstrap replicate is calibrated again, so the standard errors include the calibration.

Tests PY-CALIB-003 and 004, PY-TENURE-001; `traceconomics check tenure` prints each survey's
factors.

## The groups

| Grouping        | Who                                                                                     |
| --------------- | --------------------------------------------------------------------------------------- |
| A               | households ranked by net money income, a fifth of households each                       |
| B (the default) | people ranked by equivalised net money income, a fifth of people each                   |
| C               | people ranked by equivalised total spending, a fifth of people each                     |
| Tenure          | renters, owners, housed free (from the rent columns)                                    |
| Pensioners      | households whose main income source is a pension                                        |
| Household types | Eurostat's six: one, two, three or more adults, each with or without dependent children |

- **Income** is money income after taxes, without income in kind or imputed rent (Eurostat's
  disposable income). **Equivalising** uses the modified OECD scale: 1 for the first person aged
  14 or over, 0.5 for each other, 0.3 for each child under 14.
- **People quintiles, whole households.** Every member shares the household's equivalised value,
  so a household falls wholly in one fifth. Cut points are set on people (household weight times
  size); a household that straddles one goes to the fifth holding the middle of its weight; ties
  are broken by household identifier, so the result is reproducible.
- **Household types** are derived from each person's relationship and activity by Eurostat's
  written rule (a dependent child: under 16, or 16 to 24, a child of the reference person, and
  neither working nor unemployed). The survey's own type variable is compared with ours, never
  used: in the 2023 file it doesn't match the households' own sizes.
- **The 2010 survey's incomes can't rank households.** Wage earners' money income is far too low
  in that file (renters' median income about a quarter of their spending, against nine tenths in
  2009 and 2011), so its income-ranked groups aren't built and the 2009 survey stands in for them.
  Groupings not ranked by income still use 2010.
- A household that can't be placed in a grouping is left out of that grouping only.

Tests PY-GROUPS-001 to 032.

## Each group's basket

A group's share of an item is the group's total spending on it over its total spending on
everything in scope (`local/shares.py`): plutocratic weights, where a household counts in
proportion to what it spends (CPI Manual 2020, ¶1.35, ¶3.18), as in the official indices.

- **Spending concept**, an option: purchases only (the official indices' concept), or all spending,
  adding own production and income in kind, which weigh more in poorer households' budgets.
- **Imputed rent**, an option: dropped and the rest rescaled, or kept and priced with actual rents.
- Shares are computed on the finest codes and summed up the tree, so every level adds up exactly.
- **Small cells.** Each share carries the number of households in the group that reported the
  item, and Eurostat's publication tier for household surveys: under 20 "suppressed", 20 to 49
  "flagged", 50 or more "normal". A suppressed item is priced at its nearest ancestor that 20 or
  more households reported.

The sums are matrix products over households, so the same code computes the estimate and every
bootstrap replicate.

## Which survey each year uses

The weights for index year y should finally be survey y-1's pattern, the period the law asks
weights to represent (Reg. 2020/1148, Art. 3(1)(b)). That survey's microdata come out about 16
months into year y, so until then year y uses a first estimate, the newest survey available when
the year began, and is revised once when survey y-1 arrives. This is rule N, the default
(`module1/schedule.py`, release dates in `data/hbs_puf_releases.toml`). Two alternatives are
options: rule F (survey y-3, fixed and never revised) and rule U (the same year's survey, as in
studies made after the fact; not a Laspeyres-type index).

Release step `check-weights` restates rule N for the newest year and fails the build if the
outputs used another survey (`module1/weights_check.py`, PY-WCHK-001 to 003). Tests of the rules:
PY-SCHED-001 to 010.

## Pricing and price-updating

For each index year and group (`module1/weights_used.py`):

1. Each leaf is priced with its own index or, by the rules above, another one: games of chance are
   dropped where the price source has no index for them; tutoring (education not defined by level)
   is priced with secondary education, where its prices are collected; imputed rent with actual
   rents; a suppressed cell at its ancestor.
2. Each share is **price-updated** from the survey year's average prices to December of the year
   before the index year, with the index that prices it, then rescaled:
   `w = s * P(Dec y-1) / P(average of survey year)`. This is the step that turns an old survey's
   spending pattern into weights for a later year.
3. The engine chains the years at December. The index is rebased to 2025 = 100, published with two
   decimals, and rates come from the published index with one decimal, as Eurostat does.

Every option combination is computed on its own, even where two must agree (the tutoring options
before 2026), and `check-combos` confirms that they do: that catches an option passed to the wrong
place.

## Standard errors and error bands

The survey samples areas (primary sampling units) within strata, then households within areas.
Households in one area are alike, so the uncertainty comes from which areas were drawn: the
bootstrap resamples areas within each stratum (`local/bootstrap.py`; Rao and Wu 1988, in the
rescaled-weights form of Rao, Wu and Yue 1992):

```text
in each stratum h with n_h areas, draw n_h - 1 areas with replacement;
an area drawn r_hi times gets the weight factor r_hi * n_h / (n_h - 1)
```

1,000 replicates with a fixed seed, so a rerun gives the same errors. Because weights, not data,
are rescaled, the method suits statistics built on quantiles: in every replicate the households
are ranked again and the cut points move.

- **Bands** (`local/bands.py`): every replicate's shares go through the same pricing,
  price-updating and chaining as the published series; the spread of the replicates' annual rates
  is the standard error. The gap between the poorest and richest fifth is computed within each
  replicate, so their correlation is kept.
- **What the files allow:** the full design where strata and areas are in the file; the region
  standing in for the strata in 2008, labelled an approximation; no errors at all for 2017 to 2019,
  whose files have no area column. Months that depend on those years get no band, never a band
  that leaves out a source of uncertainty.
- **A lower bound:** the bands cover the sampling of households, not the sampling error of the
  price indices themselves (unpublished).

Tests PY-BOOT-001 to 010, PY-BANDS-001 to 006.

## Income limits

Where each income fifth ends, from our own survey (grouping B): the limit between two fifths is the
midpoint of the last household ranked in the lower one and the first in the upper one
(`local/groups.py`, `cut_points`), so a published limit is never one household's figure. Standard
errors come from the same bootstrap replicates, with the households ranked again in each. Limits
are rounded to the euro, and converted to purchasing power standards with the factor Eurostat uses
for the same income year (`export/site.py`, `pps_factor`, which refuses Eurostat's file if its
limits don't share one factor).

## Consistency of official figures

The second topic checks official figures against their own inputs (`module5/`): a published rate
against the index it comes from, the CPI and HICP rebuilt from their items, our household types
and spending by item against ELSTAT's own tables, and "same question, different sources" (renters,
rent, household income, unemployment). A difference is never called an error and never fails a
build: rounding is labelled by the code, every other explanation is written by hand with its
evidence (`data/m5_explanations.toml`), and until then it reads "not known yet". The site's
[method page](https://traceconomics.com/en/gr/official-figures-consistency/method/) explains each
check. Tests PY-M5-001 to 018.

---

_This page is kept in the repository, in [`wiki/Household-group-methods.md`](https://github.com/agardelakos/traceconomics/blob/main/wiki/Household-group-methods.md), and copied here automatically. Changes go through a pull request; an edit made here is replaced at the next update._
