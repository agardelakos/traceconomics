---
title: "Consistency of official figures: files"
summary: "Every check of an official figure against its own inputs, period by period, as CSV."
sources: [elstat-cpi-rates, elstat-cpi-items, eurostat-prc-hicp-minr, elstat-hbs-puf, eurostat-ilc-di01]
---
`checks.json` holds each check’s summary: what is compared, how often the two sides agree, and every difference with its cause. Each check and each question across sources also has a CSV with every period compared: the published value, the value from the inputs, the difference, whether they agree and why not. `SHA256SUMS` lists the files’ checksums.
