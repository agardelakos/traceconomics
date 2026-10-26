---
title: "Data and downloads"
summary: "Every number on this site, for every combination of options, as CSV or Parquet."
sources: [elstat-cpi-items, elstat-hbs-puf, eurostat-prc-hicp-minr, eu-vocabularies-ecoicop2]
---
### What there is

For each of the 48 settings of the options (spending concept, imputed rent, price source, weights timing, tutoring), four tables cover every group:

- **index**: each group's index, 2025 = 100 (2024 = 100 for series that end in 2024);
- **rates**: annual, monthly and annual-average rates, and the gap between the poorest and richest fifth;
- **weights used**: the price-updated weights each year used, by category, with the survey they came from;
- **contributions**: each category's contribution to each group's annual rate, and to the gap.

Every table comes as Parquet (readable with DuckDB, pandas or R). The index and rates also come as CSV for every setting, and every table as CSV for the default setting. Each row names its options in its own columns, so files can be combined.

### Flags

A `quality` column marks values to read with care: "less certain" (CPI prices for 2009–2010, from ELSTAT's original tables), "coarser detail" (HICP prices before 2015, available only for broader categories) and "low reliability" (a weights row that holds a single category reported by fewer than 20 households). The `weights_status` column says whether a year's weights are a first estimate or final.

### Checking a download

The file `SHA256SUMS` lists a checksum for every file. On most systems `sha256sum -c SHA256SUMS`, run in the download folder, checks them.

### Licence and attribution

The data on this site are published under the Creative Commons Attribution 4.0 licence (CC BY 4.0): you may reuse them, also commercially, if you credit the source. The code is published under the Apache 2.0 licence.

Prices come from ELSTAT's Consumer Price Index and Eurostat's HICP; weights are our own computation from ELSTAT's Household Budget Survey public use files. ELSTAT and Eurostat bear no responsibility for these figures.
