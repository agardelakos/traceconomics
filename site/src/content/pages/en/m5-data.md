---
title: "Consistency of official figures: files"
summary: "Every check of an official figure against its own inputs, period by period, as CSV."
sources: [elstat-cpi-rates, elstat-cpi-items, eurostat-prc-hicp-minr, eurostat-prc-hicp-iw, elstat-hbs-puf, elstat-silc-puf, eurostat-ilc-di01, eurostat-ilc-lvho02, eurostat-nama-10-co3-p3, eurostat-nasa-10-nf-tr, eurostat-une-rt-a, eurostat-cens-11htts-r2, eurostat-cens-21hhct-r3, aade-pit-stats, ec-lmp-database]
---
`checks.json` holds each check’s summary: what is compared, how often the two sides agree, and every difference with its cause. Each check and each question across sources also has a CSV with every period compared: the published value, the value from the inputs, the difference, whether they agree and why not. `SHA256SUMS` lists the files’ checksums.

### Licence and attribution of these files

The files are published under the Creative Commons Attribution 4.0 licence (CC BY 4.0), like the rest of the site's data.

Computed by TracEconomics from data of the Hellenic Statistical Authority (ELSTAT, [www.statistics.gr](https://www.statistics.gr/en/home)), Eurostat, the Independent Authority for Public Revenue (AADE, [www.aade.gr](https://www.aade.gr)) and the European Commission (DG EMPL, labour market policy database, data from the national public employment services). AADE's figures are shown as published, never modified. The other data have been modified: these comparisons are our own calculations, not official statistics. ELSTAT, Eurostat and the European Commission bear no responsibility for the result of the modification. If you reuse our files, credit TracEconomics and keep this notice.

- Source: Independent Authority for Public Revenue (AADE), www.aade.gr. Shown as published.
- Source: European Commission, DG EMPL, labour market policy database (data from the national public employment services). Data modified by TracEconomics where stated; the European Commission bears no responsibility for the derived figures.

Every source, its reuse terms and its notice are listed in [SOURCES.md](https://github.com/agardelakos/traceconomics/blob/main/SOURCES.md), in the code repository.
