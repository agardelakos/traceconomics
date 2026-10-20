---
title: "How it is measured"
summary: "Each household group gets its own basket, priced with the official item indices, in the same way as the official consumer price index."
order: 0
sources: [cpi-manual-2020, hicp-manual-2024, reg-2016-792, reg-2020-1148, elstat-cpi-qr-2026, elstat-cpi-items, elstat-hbs-puf, eurostat-equivalence-scale, reg-1982-2003, rao-wu-1988, preston-2009, eurostat-contrib-2018, jaravel-2021, bruegel-inflation-inequality, kepe-2024]
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

The weights come from a sample, so each group's rates carry an error band: two standard errors either side, from a bootstrap that redraws the survey's sampling areas 1,000 times and ranks households into groups again each time. The band covers the sampling of households only, so it is a lower bound. The 2017–2019 surveys lack the information needed, so the years that use them have no band.

## Checks

- Rebuilt from Eurostat's own item indices and weights, our calculation gives Greece's official HICP within 0.1 points in every month; the same holds for ELSTAT's CPI from 2014 (2011–2013 used a fixed basket).
- Our reading of the survey files reproduces ELSTAT's published spending tables to the cent, and its published sampling errors for 2024 within 0.1 points.
- With Bruegel's settings, we rebuild its published Greek series within 0.1 points. KEPE's published figures differ from ours for known reasons (survey timing and detail).
- Our contributions code reproduces Eurostat's published euro-area contributions to two decimals (rounding apart).

## Where we differ from the official CPI

- Each group's weights come only from the survey, at subclass level. ELSTAT takes some weights from other sources (air fares and tolls weigh much more in its CPI than households report).
- Weights count purchases; the official index does too. Imputed rent is left out by default, as in the HICP.
- 2009–2010 rest on ELSTAT's original price tables at class level.
- Tutoring is priced with secondary education in every year; games of chance are left out before 2026.
