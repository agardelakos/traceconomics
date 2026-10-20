---
title: "Price source"
summary: "Which item indices price the baskets. Default: ELSTAT's national CPI."
order: 4
option: "price_source"
sources: [elstat-cpi-qr-2026, elstat-hicp-qr-2026, hicp-manual-2024, eurostat-prc-hicp-minr]
---
## The default: the national CPI

ELSTAT's CPI covers households resident in Greece, the same population as the household budget survey, so its item indices suit survey-based weights.

## The alternative: the HICP

Eurostat's HICP, the EU's common measure, also covers spending in Greece by visitors. Bruegel and the ECB use it in their studies. ELSTAT collects the prices for both, so from 2016 the item price changes are almost the same.

## How much it matters

Very little: with the same weights, all households' annual average inflation differs by at most 0.06 points between the two, and the gap between the poorest and richest fifth by at most 0.1 points.

Before 2015 Eurostat's Greek HICP has indices only for broader categories, so items are priced at that level ("coarser detail"). Tested on later years, pricing at that level moves the gap by at most 0.04 points. Eurostat publishes the HICP's item indices about a week after ELSTAT's CPI, so these combinations update later in the month.
