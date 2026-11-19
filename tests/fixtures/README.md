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
| `elstat_cpi05_2026_09.xlsx` | https://www.statistics.gr/en/statistics?…_documentID=114837 (CPI table 05, twelve-month rates, January 1959 to September 2026, English) | 2026-10-13 | not trimmed |
| `eurostat_prc_hicp_{minr,iw,fpd,midx,inw,fp}.tsv.gz` | https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/data/{DATASET}/?format=TSV&compressed=true | 2026-10-18, except `prc_hicp_fp` (research download of 2026-10-14) | header kept whole; rows for Greece, Cyprus and the euro area, all items and the food branch down to one subclass (plus games of chance and education not by level), units I25, I15 and RCH_A; plus the first row with an empty flagged cell |
| `eurostat_ilc_di01.tsv.gz` | https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/data/ILC_DI01/?format=TSV&compressed=true | 2026-11-05 | header kept whole; rows for Greece and Cyprus, the five fifths (`QU1`-`QU5`), top cut-offs and shares, units EUR, NAC and PPS; plus one row (Austria) with flagged cells |
| `eurostat_nama_10_co3_p3.tsv.gz` | https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/data/NAMA_10_CO3_P3/?format=TSV&compressed=true | 2026-11-08 | header kept whole; rows for Greece and Cyprus, unit CP_MEUR, every COICOP code |
| `eurostat_nasa_10_nf_tr.tsv.gz` | https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/data/NASA_10_NF_TR/?format=TSV&compressed=true | 2026-11-08 | header kept whole; rows for Greece and Cyprus, sector S14_S15, unit CP_MEUR, items B6G, B6N, P3, D61, D62; plus Cyprus's B101 for S1, paid, whose cells carry the confidentiality flag `@N` |
| `eurostat_ilc_lvho02.tsv.gz` | https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/data/ILC_LVHO02/?format=TSV&compressed=true | 2026-11-08 | header kept whole; rows for Greece and Cyprus, all household types, all poverty statuses |
| `eurostat_ilc_di03.tsv.gz` | https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/data/ILC_DI03/?format=TSV&compressed=true | 2026-11-08 | header kept whole; rows for Greece and Cyprus, all ages, both sexes together |
| `eurostat_une_rt_m.tsv.gz` | https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/data/UNE_RT_M/?format=TSV&compressed=true | 2026-11-08 | header kept whole; rows for Greece and Cyprus, all ages |
| `eurostat_une_rt_a.tsv.gz` | https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/data/UNE_RT_A/?format=TSV&compressed=true | 2026-11-08 | header kept whole; rows for Greece and Cyprus, ages 15-74 and 20-64 |
| `eurostat_cens_11htts_r2.tsv.gz` | https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/data/CENS_11HTTS_R2/?format=TSV&compressed=true | 2026-11-08 | header kept whole; rows for Greece, Cyprus and the region EL30 (Attica), all households and one-person households |
| `eurostat_cens_21hhct_r3.tsv.gz` | https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/data/CENS_21HHCT_R3/?format=TSV&compressed=true | 2026-11-08 | header kept whole; rows for Greece, Cyprus and the region EL301, all households and one-person households |
| `ec-empl_lmp_rjru.tsv.gz` | https://webgate.ec.europa.eu/empl/redisstat/api/dissemination/sdmx/2.1/data/LMP_RJRU/?format=TSV&compressed=true | 2026-11-08 | header kept whole (DG EMPL writes the key dimensions in capitals); rows for Greece and Cyprus; plus the first other row with a `z` (not applicable) cell |
| `aade_annual_reports_natural_persons_en.html` | https://www.aade.gr/en/perfomance-reports-accountability/statistics/annual-statistical-reports-natural-persons | 2026-11-08 | not trimmed |
| `aade_SD_FP_22F_3.xlsx` | https://www.aade.gr/sites/default/files/2024-05/SD_FP_22F_3.xlsx | 2026-11-08 | not trimmed (AADE's personal income tax statistics, tax year 2022) |
| `eurostat_copyright_notice_2026-11-07.html` | https://ec.europa.eu/eurostat/help/copyright-notice | 2026-11-07 | not trimmed (the archive job's copy, with a maintenance warning banner) |
| `eurostat_copyright_notice_2026-11-18.html` | https://ec.europa.eu/eurostat/help/copyright-notice | 2026-11-18 | not trimmed (the archive job's copy: no banner, a menu item renamed, the terms unchanged) |
| `elstat_terms_reuse.html` | https://www.statistics.gr/en/pneumatika-diakaiomata-kai-epanachresimopoiese-stoicheion | 2026-10-18 | not trimmed (the archive job's copy) |
| `ec_legal_notice.html` | https://commission.europa.eu/legal-notice_en | 2026-11-18 | not trimmed |
| `elstat_calendar_2026-11-10.html` | https://www.statistics.gr/en/calendar | 2026-11-10 | not trimmed (the archive job's copy: 2026's rows, one of them with a mistyped date, and the links to the yearly PDFs) |
| `elstat_calendar_2024-12-14.html` | https://web.archive.org/web/20241214173822id_/https://www.statistics.gr/en/calendar | 2026-11-19 | not trimmed (the Wayback Machine's copy of 2024-12-14, as captured: 2024's rows, dates written `4/1/2024`) |
| `elstat_calendar_2024_en.pdf` | https://www.statistics.gr/documents/20181/18165299/HMEROLOGIO_ANAKOINOSEON_2024_EN.pdf/37e658d2-e9c3-af47-f34b-d97ed7ca6706 | 2026-11-19 | not trimmed (ELSTAT's releases calendar 2024) |
| `elstat_calendar_2026_en.pdf` | https://www.statistics.gr/documents/20181/16784295/CALENDAR_2026_ENG.pdf/a575145b-6a6b-403e-2a00-579ab0e568bd | 2026-11-19 | not trimmed (ELSTAT's releases calendar 2026) |
| `elstat_calendar_2027_en.pdf` | https://www.statistics.gr/documents/20181/16784295/RELEASES_CALENDAR_2027_EN.pdf/c9f54e57-dae5-33f1-0722-122b00116ff8 | 2026-11-19 | not trimmed (ELSTAT's releases calendar 2027) |
| `eurostat_v1_gr_{minr,iw}.tsv.gz` | same Eurostat bulk files (`prc_hicp_minr`, `prc_hicp_iw`) | 2026-10-18 | Greece only. minr: unit I25 for every category, plus RCH_A for all items, periods from 2014-12. iw: every category, years from 2015 |

Source: ELSTAT (Hellenic Statistical Authority), www.statistics.gr, Eurostat and the European
Commission, reused under their reuse policies (see SOURCES.md). The files marked "not trimmed" are stored exactly as
published. The others were modified by TracEconomics: shortened to the parts the tests read,
with the content of the kept parts unchanged. ELSTAT and Eurostat bear no responsibility for
the result of the modification.

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
| `elstat_cpi05_2026_09.xlsx` | `28c992705281c33702a98d798b6a6aa28a017f4a4563306fe107a0c8f2f0fbf3` |
| `aade_annual_reports_natural_persons_en.html` | `a125dd2e91d9837bf0783557dd5f6a62e43721bb59ddee4cea5dd09e1de374ad` |
| `aade_SD_FP_22F_3.xlsx` | `777321bcbe3c652315e4eef0bb5e1bfe9a7e8a3c34e89fe0cf957aaeb9c34136` |
| `eurostat_copyright_notice_2026-11-07.html` | `83f0ec245915182f6eb7d400c16f96f0ddc42d7710b7f815a4bb3cecf6a23fbe` |
| `eurostat_copyright_notice_2026-11-18.html` | `9a2468f5eb1c7efa5cc4c86fbf039911574cdcd4b9103c57d607c0f374c6199b` |
| `elstat_terms_reuse.html` | `29fbad03a13fb5c22d53f931b03b2df6a31b4994642f4531e2fc7a769dd57b88` |
| `ec_legal_notice.html` | `82502bd4686fdd437beea1156fc9cb306bbdbd38304fd4ea3767aca8c7d1c1f9` |
| `elstat_calendar_2026-11-10.html` | `55311736c9eab0da4426abce2e0677f335a319575b0f0866bda6ac1d55f83aa4` |
| `elstat_calendar_2024-12-14.html` | `9bb09ea94428479c53b7c5dbfa08ba2d83737a90a5db28cffb13a082eaea6717` |
| `elstat_calendar_2024_en.pdf` | `bdd8288cd1afc078ec20d8b7b4dfd903196c03aae8a59c392b54497a99eb9459` |
| `elstat_calendar_2026_en.pdf` | `f6def361a0456cbcd9eedaedb9f33f0b9f613d3fb8c6ea777ab22cd320401798` |
| `elstat_calendar_2027_en.pdf` | `f6a48cc5ca05a1a198983f524b4ffb142c4df8ee54f65c7c5b7731102e0f556d` |
