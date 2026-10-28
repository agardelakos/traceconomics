---
title: "How it is measured"
summary: "Each household group gets its own basket, priced with the official item indices, in the same way as the official consumer price index."
order: 0
sources: [cpi-manual-2020, hicp-manual-2024, reg-2016-792, reg-2020-1148, elstat-cpi-qr-2026, elstat-cpi-items, elstat-hbs-puf, eurostat-equivalence-scale, reg-1982-2003, rao-wu-1988, preston-2009, eurostat-contrib-2018, jaravel-2021, bruegel-inflation-inequality, kepe-2024, eurostat-energy-2022, ecb-op330-2023]
---
## In one paragraph

The official consumer price index measures inflation for the average household's basket. This site builds the same kind of index for groups of households, each with its own basket: the poorest and richest fifth of people, renters and owners, pensioner households. Prices are the official item indices; only the weights change from group to group. Everything is computed from public files, and every number can be rebuilt from them.

## Prices

By default, prices are ELSTAT's consumer price index item indices (its table 07), which ELSTAT re-issued in today's classification back to 2010. For 2009–2010 we use ELSTAT's original tables, kept by the Wayback Machine's copy of its old site; they are an older version of the prices, so those months are marked "less certain". Their item numbers follow a national list, so they are matched to today's categories at class level, never by number.

The alternative is Eurostat's HICP item indices for Greece.

## Weights

Each group's weights come from ELSTAT's household budget survey public use files, 2008 to 2024:

- **Each group's own shares.** We add up the group's spending on each item and divide by its total spending (plutocratic weighting, as official indices do), at the finest detail available (subclass, five digits).
- **One classification.** Surveys before 2024 use the 1999 classification; they are converted to COICOP 2018 with the EU's official correspondence, splitting codes in proportion to Greece's 2025 weights.
- **Moved to current prices.** Shares are price-updated to December of the year before, as ELSTAT does.
- **Which survey.** By default a year uses the survey of the year before (rule N). See the option pages for the alternatives.
- **What's left out.** Items the public files don't record (1.2–6.4% of purchases, depending on the year) are dropped and the other shares rescaled. Hospital services are missing from the 2008–2014 files: putting them back changes the groups' annual-average rates by at most 0.11 points, and the figures that rest on those surveys carry a footnote.
- **Small cells.** An item reported by fewer than 20 sampled households in a group is priced at a broader level and published only together with its neighbours (Eurostat's publication guideline).
- **Special items.** Games of chance have no price index before 2026 and are left out until then. Education not defined by level (mostly tutoring) has no index of its own and is priced with secondary education, where ELSTAT collects tutoring prices.

## Groups

- **Income fifths.** People ranked by equivalised income: the household's money income after taxes (without income in kind or imputed rent), divided by the modified OECD scale. Each fifth holds the same number of people.
- **Tenure.** Renters, owners and rent-free households, from the survey's rent records.
- **Pensioner households.** Households whose main income source is a pension.
- **All households,** computed the same way, as the benchmark.

## From index to rates

Each year's index is linked to the previous one at December (chain-linking). The index is set to 100 for the 2025 average and published with two decimals; rates are computed from the published index and shown with one decimal, as official statistics do. The gap between the poorest and richest fifth is the difference of their rates as shown.

Each category's contribution to an annual rate follows Eurostat's method, so contributions add up to the rate.

## Uncertainty

The weights come from a sample, so each group's rates carry an error band: two standard errors either side, from a bootstrap that redraws the survey's sampling areas 1 000 times and ranks households into groups again each time. The band covers the sampling of households only, so it is a lower bound. The 2017–2019 surveys lack the information needed, so the years that use them have no band.

## Checks

- Rebuilt from Eurostat's own item indices and weights, our calculation gives Greece's official HICP within 0.1 points in every month; the same holds for ELSTAT's CPI from 2014 (2011–2013 used a fixed basket).
- Our reading of the survey files reproduces ELSTAT's published spending tables to the cent (except in 2014, 2015 and 2018; see below), and its published sampling errors for 2024 within 0.1 points.
- With Bruegel's settings, we rebuild its published Greek series within 0.1 points. KEPE's published figures differ from ours for known reasons (survey timing and detail).
- Our contributions code reproduces Eurostat's published euro-area contributions to two decimals (rounding apart).

## Where we differ from the official CPI

- Each group's weights come only from the survey, at subclass level. ELSTAT takes some weights from other sources (air fares and tolls weigh much more in its CPI than households report).
- Weights count purchases; the official index does too. Imputed rent is left out by default, as in the HICP.
- 2009–2010 rest on ELSTAT's original price tables at class level.
- Tutoring is priced with secondary education in every year; games of chance are left out before 2026.

## What ELSTAT has not confirmed

Some points rest on our reading of the public evidence, because ELSTAT hasn't said. None of them changes how the figures are computed; each changes how far you can rely on one explanation.

- **Cash help with energy and food bills.** The per-kWh electricity bill subsidy and the heating-oil subsidy lowered the price households paid, and ELSTAT's indices show it: in September 2022 its electricity index could only fit a price net of the subsidy. Power Pass, Fuel Pass and Market Pass were different: money paid to households, not lower prices. Under Eurostat's rules a price index leaves out such payments, so we take it that ELSTAT's indices do too, but ELSTAT has never said, and no public list of what each country included exists. So our figures, like the official ones, show what prices did, not how much households were helped.
- **Items missing from the public files.** Tolls, life insurance, some "various services" and a few other items are not in the survey's public files. ELSTAT hasn't said why. We leave them out and publish the share that is missing.
- **Survey weights in 2014, 2015 and 2018.** In these three years the household weights in the public files differ from the ones behind ELSTAT's published tables, and ELSTAT hasn't explained why. We use the files' weights as they are, since they are consistent within each file.
- **Tutoring from 2026.** ELSTAT's 2026 CPI gives tutoring and language schools no weight, though it still collects their prices; it hasn't said why. See the tutoring option.
- **Money paid to other households from 2024.** Whether the survey now takes it off income is not stated. See the income groups option.
- **ELSTAT's own weights for 2021–2023.** For the COVID years, ELSTAT's published CPI weights for 2022 and 2023 fit a survey two years old moved forward to the year before, the timing our default uses, but ELSTAT hasn't described its method, and for 2021 the evidence doesn't settle it. This affects only how closely our default follows ELSTAT's practice, not our figures.
