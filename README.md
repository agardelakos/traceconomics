# Traceconomics

An open, transparent tracker of the economy, built only on public data. Greece first, designed for many countries.

**Status: in development, not yet published.** What works:
- an archive job that keeps every published version of the source statistics;
- a store and calculation engine that rebuild the official Greek inflation figures from their published parts;
- inflation by household group for Greece (income fifths, renters and owners, pensioner households), monthly from 2010, under every combination of the method options, with error bands;
- a bilingual website (Greek and English) with the charts, the option switches, a personal inflation calculator and a glossary, built and checked locally.

## Why an archive first

Statistical offices revise their numbers and overwrite their files. Some Greek CPI tables, for example, are replaced in place every month. Without a copy of each version, nobody can later check what was known on a given date. So the archive comes first, and every number this project publishes will trace back to a file in it.

## What the archive job does

On each release day it fetches, from 13:00 Greek time (an hour after both publishers release):

- **ELSTAT** (Hellenic Statistical Authority): the consumer price index, harmonised index and household budget survey publication pages and every file they list, the release calendar, and the catalogue of microdata files.
- **Eurostat**: the HICP datasets for all countries (indices, item weights, first releases), downloaded only when Eurostat's "last data update" time changes, and the HICP methodology notes.
- **Both publishers' reuse terms**, with an alert when they change.

Every file is stored exactly as received, with a manifest (URL, time, HTTP headers, SHA-256). A new copy is kept only when the content changed. Nothing is ever overwritten or deleted. Each run ends with a short report by email, or in an `outbox/` folder if email isn't set up.

Fetching is deliberately polite: one request at a time with a pause, a User-Agent naming the project, and `robots.txt` respected.

## From archive to numbers

- **The store** (`python -m traceconomics store update`) reads every archived file once and keeps each published value, with when the source published it, when we fetched it, and every later revision or withdrawal. So it can answer "what was known on a given date?". It's a cache: it can be deleted and rebuilt from the archive at any time.
- **The parsers** read Eurostat's bulk HICP files and ELSTAT's yearly consumer price index tables. A file that doesn't look as expected stops the build, rather than being guessed at.
- **The engine** links each year's index to December of the previous year and chains the years, as the HICP and the Greek CPI are built.
- **The engine is checked against official figures** before it is used for anything else:
  - `python -m traceconomics check v1` rebuilds Greece's all-items HICP from Eurostat's own sub-indices and weights;
  - `python -m traceconomics check v1-cpi` rebuilds the Greek CPI from ELSTAT's item indices and weights.

  Both match the official annual rates to within 0.1 percentage points in every month checked. That's the most that rounding of the published inputs allows.

## The website

`site/` is a static website built with Astro and Observable Plot, in Greek (`/el/`) and English (`/en/`). It shows pre-computed series only; the browser computes nothing but the personal calculator, and that calculator, left untouched, reproduces the official series to the last digit (a test checks it). There are no cookies, no tracking and no requests to other sites.

The site reads files written by the pipeline. The group series need the household budget survey microdata, which are processed locally and never published; only group totals and shares are.

```sh
python -m traceconomics module1 run --out ~/traceconomics-outputs           # every group and option combination
python -m traceconomics export site --out site/public/data        # the website's data files, labels and sources
cd site
npm ci                                                  # exact versions from package-lock.json
npm run check                                           # type check, tests (incl. calculator parity), build, site checks
npm run preview                                         # look at it on http://localhost:4321
npm run a11y                                            # accessibility check (axe), with the preview running
```

`npm run check` fails on a missing translation, an unknown source, an inline script, a resource from another site, or a page over its size budget. Building needs Node.js 22 or later.

## Install

Requires Python 3.14.

```sh
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"     # on Linux/macOS: .venv/bin/python
```

Copy `config.example.toml` to your user config folder (`%APPDATA%\traceconomics\config.toml` on Windows, `~/.config/traceconomics/config.toml` on Linux) and edit it. To send reports by email, fill in the `[email]` section and store the password with `python -m keyring set traceconomics-smtp <username>`.

## Use

```sh
python -m traceconomics archive            # run if a release is due (what the scheduler calls)
python -m traceconomics archive --dry-run  # show what would be fetched
python -m traceconomics archive --force    # run now regardless
python -m traceconomics status             # last runs, next release days, files waiting for backup
python -m traceconomics backup-done        # record that you've just backed up the archive
python -m traceconomics import FILE        # add a file downloaded by hand (e.g. microdata needing a login)
python -m traceconomics seed FOLDER        # copy earlier downloads whose URL, date and checksum are recorded
python -m traceconomics fetch-history cpi07 --years 2011-2013   # one-off, slow: past years of ELSTAT's CPI table 07
python -m traceconomics notify-test        # check that reports reach you
python -m traceconomics schedule install   # Windows: register the daily trigger in Task Scheduler
python -m traceconomics store update       # read new archived files into the store (`rebuild` starts over)
python -m traceconomics check v1           # rebuild the official HICP from its parts (`v1-cpi`: the Greek CPI)
python -m traceconomics export site --out site/public/data       # the files the website reads
```

The job is triggered daily but only works on release days (read from both publishers' calendars). A day the computer was off is caught up at the next trigger and reported as missed.

## Tests

```sh
python -m pytest
```

The tests use small saved extracts of real pages (`tests/fixtures/`) and never touch the network.

## Data sources

- ELSTAT, Hellenic Statistical Authority, https://www.statistics.gr. Source: ΕΛΣΤΑΤ. Reused under ELSTAT's reuse policy.
- Eurostat, https://ec.europa.eu/eurostat. Reused under Eurostat's copyright notice. Eurostat bears no responsibility for anything derived from its data here.
- Publications Office of the European Union, EU Vocabularies: the English and Greek names of the spending categories (ECOICOP version 2).

## Licence

Code: [Apache-2.0](LICENSE). Data published by this project: CC BY 4.0.
