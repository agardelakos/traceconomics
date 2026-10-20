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

## Untouched files

These files are stored exactly as the publisher served them, byte for byte (see
`.gitattributes`: git never converts their line endings). Anyone can download the source again
and compare hashes. `tests/test_fixtures.py` checks that the stored files still have these hashes.

| File | SHA-256 |
|---|---|
| `elstat_puf_catalogue.html` | `5c8e1dd4b77cba49a4c37f9bfe596f3b18c0f04daa352670ffc4652b880ef64e` |
| `eurostat_dataflow_prc_hicp_minr.xml` | `a596c37a894355954184b09b0963640d6bc3bc3589ea414635adfc2935893ee7` |
| `elstat_cpi07_2025.xls` | `0ac766c66db2f77964b7ae72015851636d12649476387b21d58c6fe43686c0f1` |
| `elstat_hbs_t103_2018.xls` | `91dd130659c0c165ef643fe5dcf28c51c5de86aac8c6f4440c353142bbc4151a` |
| `elstat_hbs_t103_2024.xlsx` | `cfccb45f78bedf799b71c7f589e36cb33b1d14986037c9a1f2c7b0b28c46b345` |
| `elstat_cpi07_2026.xlsx` | `11baa71c365f5203f36ba5e9745e31df38ead23a3bb9e5ac27cf439fc0448593` |
| `elstat_cpi07_2011_el.xls` | `6f7496fe0925d0ac7931264e6cfb338ceff7f890d9f8af033f9e234499f74eb7` |
