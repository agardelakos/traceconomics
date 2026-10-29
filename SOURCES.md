# Sources and reuse terms

TracEconomics publishes figures computed from public data only. This file lists every source the published figures and the website are built from, the reuse terms each publisher sets, and how we meet them.

The terms below were read on 2026-10-28. The archive job fetches the publishers' terms pages on every run and raises an alert when one changes, so a change is read before the next release.

## Our licences

- **Data we publish:** [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). It covers our own work: the series, weights and tables we compute. The source data stay under their publishers' terms, below.
- **Code:** [Apache-2.0](LICENSE), with the notices in [NOTICE](NOTICE).

## The notice we give

Every published dataset carries this notice, in its `metadata.json` and on the site's data page:

> Computed by TracEconomics from data of the Hellenic Statistical Authority (ELSTAT, www.statistics.gr) and Eurostat. The data have been modified: these are our own calculations, not official statistics. ELSTAT and Eurostat bear no responsibility for the result of the modification.

If you reuse our files, credit TracEconomics and keep this notice.

## ELSTAT (Hellenic Statistical Authority), www.statistics.gr

**Terms:** ELSTAT, "Copyright and reuse of data" (PDF linked from https://www.statistics.gr/en/pneumatika-diakaiomata-kai-epanachresimopoiese-stoicheion). Reuse is free, also commercially, without a written licence, provided that:

- the source is indicated;
- any modification of the data or text, including translation, is stated clearly to the end user, together with a statement that ELSTAT bears no responsibility for the result of the modification;
- links to ELSTAT's website mention www.statistics.gr clearly and in full.

ELSTAT's logo and third-party material are excluded. We use neither.

**What we use:**

| Data | How we use it | Modified? |
|---|---|---|
| Consumer Price Index, item indices (table 07), from 2011 | Prices for the default series | Yes: chain-linked and weighted into indices by group |
| Consumer Price Index, original tables for 2009–2010 | Prices for those years. ELSTAT no longer publishes them; the files are ELSTAT's own, retrieved from the Internet Archive's Wayback Machine copy of ELSTAT's old website | Yes, as above |
| Consumer Price Index, twelve-month rates of the overall index (table 05) | Shown beside our own calculation of the same rate, as a check | No: shown as published |
| Household Budget Survey public use files, 2008–2024 | Spending weights by household group | Yes: we compute aggregates. The microdata files are never redistributed |
| Household Budget Survey 2024 press release, coefficients of variation (table 17) | Checks of our standard errors only | Not published |
| Household Budget Survey published tables (table 1.03) | Checks of our weights; names of the spending categories that the EU vocabulary lacks | Names as published; a name in capitals is replaced by its single sub-category's name when the two are the same words |

**Notice:** "Source: Hellenic Statistical Authority (ELSTAT), www.statistics.gr. Data modified by TracEconomics; ELSTAT bears no responsibility for the result of the modification."

## Eurostat

**Terms:** Eurostat, "Copyright notice and free re-use of data", https://ec.europa.eu/eurostat/help/copyright-notice, implementing the European Commission's reuse policy (Commission Decision 2011/833/EU). Reuse of statistical data is authorised, also commercially, provided that:

- the source is acknowledged;
- modifications of the data are stated clearly to the end user;
- a disclaimer of Eurostat's non-responsibility is included.

Data for countries outside the EU, EFTA and the EU's acceding and candidate countries may not be reused commercially. Our published files hold no such data.

**What we use:**

| Dataset | How we use it | Modified? |
|---|---|---|
| HICP item indices, `prc_hicp_minr` ([doi:10.2908/PRC_HICP_MINR](https://doi.org/10.2908/PRC_HICP_MINR)) | Prices for the HICP option | Yes: chain-linked and weighted into indices by group |
| Distribution of income by quantiles, `ilc_di01` (EU-SILC) | The income cut-offs that place a household in its fifth | No: shown as published |
| Other HICP datasets (`prc_hicp_midx`, `prc_hicp_iw`, `prc_hicp_inw`, `prc_hicp_fpd`, `prc_hicp_fp`) | Checks of our calculations only | Not published |

**Notice:** "Source: Eurostat. Data modified by TracEconomics; Eurostat bears no responsibility for the derived figures." Eurostat's suggested citation for a dataset is its DOI and the access date; each dataset's `metadata.json` lists the exact files and dates used.

## Eurostat and the Publications Office of the European Union: EU Vocabularies

**Terms:** ECOICOP is maintained by Eurostat, its author, and published by the Publications Office on the EU Vocabularies website. No licence is stated for version 2 itself, so we follow the terms that apply to it as Eurostat's work: Eurostat's copyright notice (above) and the European Commission's reuse policy (Commission Decision 2011/833/EU), which the EU open data portal records as the licence of ECOICOP version 1 (https://data.europa.eu/data/datasets/ecoicop). Both allow reuse with credit; changes must be indicated, with a disclaimer of responsibility.

**What we use:** the English and Greek names of the spending categories, ECOICOP version 2 (the EU's version of COICOP 2018), read from the Publications Office's SPARQL endpoint (https://publications.europa.eu/webapi/rdf/sparql).

**Modified:** we take off the code number at the start of each name and the marker of the kind of product at its end, for example "(ND)" for non-durable. The words of the names are unchanged; they are the EU's official translation, never ours.

## Copies in this repository

The tests run offline, on small copies of the publishers' own files in `tests/fixtures/`: ELSTAT's CPI and household budget survey tables, pages from its website and release calendar, and extracts of Eurostat's HICP files, metadata and release calendar. Each file's source address and retrieval date are listed in `tests/fixtures/README.md`.

**Modified?** Some are stored exactly as published, byte for byte, and checked against their hashes. The others are shortened to the parts the tests read; the content of the kept parts is unchanged.

**Notice** (also in `tests/fixtures/README.md`): "Source: ELSTAT (Hellenic Statistical Authority), www.statistics.gr, and Eurostat. The shortened files were modified by TracEconomics; ELSTAT and Eurostat bear no responsibility for the result of the modification."

## What we never publish

- **Survey microdata.** ELSTAT's public use files are used on our own machines only. We publish aggregates computed from them, never the files or any record from them.
- **Eurostat data for countries outside the EU, EFTA and the candidate countries.**
- **Publishers' logos.**

## Works cited

The methods, manuals and papers behind each page are listed on that page and in the site's bibliography (`/data/v1/references.json`). They are cited, not reused.
