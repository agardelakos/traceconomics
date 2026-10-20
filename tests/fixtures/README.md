# Test fixtures

Small extracts of real pages, trimmed to the parts the parsers read. They let the
tests run without network access and fail if a parser stops understanding a format.

| File | Source | Retrieved | Trimmed to |
|---|---|---|---|
| `elstat_cpi_page.html` | https://www.statistics.gr/en/statistics/-/publication/DKT87/- | 2026-10-13 | 6 table rows with document links |
| `elstat_calendar.html` | https://www.statistics.gr/en/calendar | 2026-10-13 | the first 40 release rows of 2026, plus the household budget survey row |
| `elstat_puf_catalogue.html` | https://www.statistics.gr/spuf-rep/puf_en.jsp | 2026-10-17 | not trimmed |
| `eurostat_dataflow_prc_hicp_minr.xml` | https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/dataflow/ESTAT/PRC_HICP_MINR/latest | 2026-10-18 | not trimmed |
| `eurostat_calendar.json` | https://ec.europa.eu/eurostat/o/calendars/eventsJson (Euro indicators, 2026-10-01 to 2026-12-31) | 2026-10-18 | 4 inflation events and 2 others |
| `elstat_cpi07_2025.xls` | https://www.statistics.gr/en/statistics?…_documentID=554284 (CPI table 07, 2025, English) | 2026-10-13 | not trimmed (binary Excel) |
| `elstat_hbs_t103_2018.xls` | https://www.statistics.gr/en/statistics?…_documentID=481226 (HBS table 1.03, 2018, English) | 2026-10-13 | not trimmed |
| `elstat_hbs_t103_2024.xlsx` | https://www.statistics.gr/en/statistics?…_documentID=573851 (HBS table 1.03, 2024, English) | 2026-10-13 | not trimmed |
| `elstat_cpi07_2026.xlsx` | https://www.statistics.gr/en/statistics?…_documentID=585819 (CPI table 07, 2026, English) | 2026-10-13 | not trimmed |
| `elstat_cpi07_2011_el.xls` | https://www.statistics.gr/en/statistics?…_documentID=114857&…_locale=el (CPI table 07, 2011, Greek) | 2026-10-18 | not trimmed |
| `eurostat_prc_hicp_{minr,iw,fpd,midx,inw,fp}.tsv.gz` | https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/data/{DATASET}/?format=TSV&compressed=true | 2026-10-18, except `prc_hicp_fp` (research download of 2026-10-14) | header kept whole; rows for Greece, Cyprus and the euro area, all items and the food branch down to one subclass (plus games of chance and education not by level), units I25, I15 and RCH_A; plus the first row with an empty flagged cell |
| `eurostat_v1_gr_{minr,iw}.tsv.gz` | same Eurostat bulk files (`prc_hicp_minr`, `prc_hicp_iw`) | 2026-10-18 | Greece only. minr: unit I25 for every category, plus RCH_A for all items, periods from 2014-12. iw: every category, years from 2015 |

Source: ELSTAT (Hellenic Statistical Authority) and Eurostat, reused under their reuse
policies. The files were shortened; the content of the kept parts is unchanged.
