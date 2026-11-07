# Adding a source or a country

**Start with an issue.** A new source or country is discussed before any code: which files, under
which reuse terms, at what level of detail, and which method choices it needs. The design allows
new countries without a redesign, but each one's sources are checked on paper first. Please don't
send a pull request for a new country or source without an agreed issue.

## The multi-country design

- **Country codes are ISO 3166-1 alpha-2** in every ID, path and URL (`GR` in data, `gr` in site
  addresses). A source that uses other codes is translated once, at the boundary, in
  `src/traceconomics/data/geo.toml` (for example Eurostat's `EL` becomes `GR`). Groups of countries
  (euro area, EU) are kept as published and never mistaken for a country.
- **The archive and the store hold every country** a source publishes, not only the ones on the
  site. Eurostat's harmonised price indices are already archived for all countries.
- **The site is country first**: `/{lang}/{country}/{topic}/`. A country's texts are its own; the
  build refuses to reuse another country's.
- **Options that can't be computed** for a country or period are shown greyed, with the reason.
  The data model stores, per country and year, which options are available and why not.
- **Each country's language and English.** A new country brings its language's texts, and a
  native speaker's review before that language is offered.

## How a source works

A source is an adapter in `src/traceconomics/sources/`: one module or package per publisher
(`elstat/`, `eurostat/`). It has three jobs.

1. **Find and fetch.** It knows the publisher's pages, files or API, and its release calendar (so
   the job runs on release days). It fetches through the shared client in `sources/base.py`
   (`RunContext`), which is polite by construction: one request at a time, a pause, a User-Agent
   naming the project, retries with growing waits, `robots.txt` respected. Prefer bulk files and
   download only when the publisher's update time changed.
2. **Archive.** Every file goes into the raw archive as received, with a manifest. For web pages
   the adapter hashes the extracted content rather than the raw HTML, so session tokens and
   timestamps don't count as a change.
3. **Parse.** A parser reads an archived file into the store's long format: one value per series
   and period, the value exactly as published next to the number, and the publisher's flags. Each
   parser has a `PARSER_VERSION`; bumping it makes the store re-read that dataset.

Also needed:

- **Reuse terms.** The publisher's terms page is added to `sources/terms.py`, so a change raises an
  alert, and the source, its terms and our notice go into `SOURCES.md`. Paywalled data, and data
  whose terms forbid redistribution, can't be used.
- **Catalog entry.** Which archived datasets are parsed, by which parser, with which series key, is
  data in `src/traceconomics/data/datasets.toml`, read by `catalog.py`. The key order there is
  fixed once chosen: it builds keys and file names.
- **Codes at the boundary.** Spending categories are stored as plain COICOP digits (`01111`), with
  `TOTAL` for all items; a source's own prefixes are removed in the parser. Country codes go
  through `geo.toml`.

## Format checks: refuse surprises

A parser checks every assumption it relies on (header, columns, code lists, units, period
formats) with `checks.require(...)` and raises `checks.FormatError` with a readable message when
one fails (`checks.examples()` lists the offending values). It never guesses, skips a row it
doesn't understand, or fills a gap. A publisher's layout change then stops the run, and a person
looks, instead of numbers that look right and aren't reaching the site.

## Fixtures and tests

- Each parser is tested on a **small saved extract of a real file** in `tests/fixtures/`, trimmed
  to the parts the parser reads, or kept whole if small. Tests never touch the network.
- Each fixture gets a row in `tests/fixtures/README.md`: source URL, retrieval date, what was
  trimmed. A file kept exactly as published is listed with its SHA-256 under "Untouched files" and
  checked by `tests/test_fixtures.py`. Never re-save or convert a fixture; git stores them byte for
  byte (`.gitattributes`).
- Test the failure paths too: a changed header or an unknown code must raise `FormatError`.
- Microdata never go into fixtures or tests; build a small synthetic survey in the test.

## Before numbers are used

A new source's figures are checked against the publisher's own aggregates before anything is built
on them (see the `check` commands in the README). Differences are reported and explained, never
tuned away.

---

*This page is kept in the repository, in [`wiki/Adding-a-source-or-country.md`](https://github.com/agardelakos/traceconomics/blob/main/wiki/Adding-a-source-or-country.md), and copied here automatically. Changes go through a pull request; an edit made here is replaced at the next update.*
