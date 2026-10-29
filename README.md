# TracEconomics

[![tests](https://github.com/agardelakos/traceconomics/actions/workflows/tests.yml/badge.svg?branch=main)](https://github.com/agardelakos/traceconomics/actions/workflows/tests.yml)

An open, transparent tracker of the economy, built only on public data. Greece first, designed for many countries.

**The site: [traceconomics.com](https://traceconomics.com).** What it does today:
- an archive job that keeps every published version of the source statistics;
- a store and calculation engine that rebuild the official Greek inflation figures from their published parts;
- inflation by household group for Greece (income fifths, renters and owners, pensioner households), monthly from 2010, under every combination of the method options, with error bands;
- the website, with the charts, the option switches, a personal inflation calculator and a glossary. It is built in English and Greek; the Greek version opens after a final read.

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

`site/` is a static website built with Astro and Observable Plot, in Greek (`/el/`) and English (`/en/`). It shows pre-computed series only; the browser computes nothing but the personal calculator, and that calculator, left untouched, reproduces the official series to the last digit (a test checks it). There are no cookies and no requests to other sites, except one: the published site counts visits with Cloudflare Web Analytics (cookieless, totals only), added only in release builds.

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

`npm run check` fails on a missing translation, an unknown source, an inline script, a resource from another site, or a page over its size budget. Building needs Node.js 22 or later. More on running and checking the site: [site/README.md](site/README.md).

## Install

Requires Python 3.14. Install from the lock file, which pins every package and checks it against its hash, then the project itself:

```sh
python3.14 -m venv .venv
.venv/bin/python -m pip install --require-hashes --no-deps -r requirements-dev.txt
.venv/bin/python -m pip install --no-deps --no-build-isolation -e .
```

On Windows the interpreter is `.venv\Scripts\python`. The microdata steps (household weights, error bands) also need the `local` extra: use `requirements-local.txt` instead.

Copy `config.example.toml` to your user config folder (`~/.config/traceconomics/config.toml` on Linux, `%APPDATA%\traceconomics\config.toml` on Windows) and edit it. To send reports by email, fill in the `[email]` section and store the password with `python -m keyring set traceconomics-smtp <username>`.

## Use

Every command has `--help`. What each part of the package does: [src/traceconomics/README.md](src/traceconomics/README.md).

**The archive**

```sh
python -m traceconomics archive            # run if a release is due (what the daily trigger calls)
python -m traceconomics archive --dry-run  # show what would be fetched
python -m traceconomics archive --force    # run now regardless
python -m traceconomics import FILE        # add a file downloaded by hand (e.g. microdata needing a login)
python -m traceconomics seed FOLDER        # copy earlier downloads whose URL, date and checksum are recorded
python -m traceconomics fetch-history cpi07 --years 2011-2013   # one-off, slow: past years of ELSTAT's CPI table 07
```

**From the archive to the published files**

```sh
python -m traceconomics store update       # read new archived files into the store (`rebuild` starts over)
python -m traceconomics weights run        # spending shares by group, from the survey microdata (local extra)
python -m traceconomics bands run          # error bands for the group series (local extra)
python -m traceconomics module1 run --out ~/traceconomics-outputs   # every group and option combination
python -m traceconomics export site --out site/public/data           # the files the website reads
python -m traceconomics mapping build --out src/traceconomics/data  # rebuild the mapping tables (local extra)
```

**Checks** (`python -m traceconomics check <name>`)

| Name | What it checks |
|---|---|
| `v1`, `v1-cpi` | The engine rebuilds Greece's official HICP (from Eurostat's parts) and CPI (from ELSTAT's) |
| `v2` | The survey microdata rebuild ELSTAT's published household spending (local extra) |
| `mapping` | The survey's old codes mapped to COICOP 2018, against the next year (local extra) |
| `v3` | Our all-households series against the official CPI |
| `v4`, `v5` | Other studies' Greek series, rebuilt with their own settings, and ours against them one setting at a time |
| `v6` | Eurostat's contributions of each division to the euro area's rate, rebuilt |
| `prices`, `seam`, `hospital` | Reports: CPI against HICP prices, the 2010 seam between ELSTAT's old and new tables, the effect of hospital services |
| `combos` | Every option combination: identities that must hold, and how much each option moves the result |

**Running it**

```sh
python -m traceconomics status             # last runs, next release days, files waiting for backup
python -m traceconomics notify-test        # check that reports reach you
python -m traceconomics backup-done        # record that you've just backed up the archive
python -m traceconomics backup sync        # copy new archive files to cloud storage (`plan`: list them; never microdata)
python -m traceconomics analytics export   # the site's daily visit counts into the archive (the daily run does this)
python -m traceconomics release build      # recompute, check, build the site, upload a private preview
python -m traceconomics release promote ID --to staging|production   # publish a build (`release status` lists them)
python -m traceconomics schedule units --out ~/.config/systemd/user   # Linux: the daily timer (see below)
python -m traceconomics schedule install   # Windows: the daily trigger in Task Scheduler
```

The job is triggered daily but only works on release days (read from both publishers' calendars). A day the computer was off is caught up at the next trigger and reported as missed.

## Run it on a Linux server

On a server the pipeline runs inside the official Python image, pinned by digest, so it uses exactly the interpreter and libraries the tests ran on. Results are byte-identical across machines: the same archive gives the same files on Windows and on Linux, on x86 and on Arm.

One-time setup, as an ordinary user (not root), with Docker installed and that user in the `docker` group:

```sh
git clone <this repository> ~/traceconomics
# Node.js for the site build, unpacked to ~/traceconomics-node (check its SHA-256 against nodejs.org)
IMAGE=python:3.14.8-slim@sha256:a2b82f3c48559aa0a8446d9af49826b6e2b2016f4cd2afabfe6013ec53729170
docker run --rm --user "$(id -u):$(id -g)" -v "$HOME:$HOME" -e "HOME=$HOME" -w "$HOME/traceconomics" $IMAGE \
  sh -c 'python -m venv ~/traceconomics-venv &&
    ~/traceconomics-venv/bin/pip install --require-hashes --no-deps -r requirements-local.txt &&
    ~/traceconomics-venv/bin/pip install --no-deps --no-build-isolation -e .'
# config: ~/.config/traceconomics/config.toml (see config.example.toml, including [release])
# secrets: ~/.config/traceconomics/env, mode 600, one NAME=value per line (names in config.example.toml)
docker run --rm --user "$(id -u):$(id -g)" -v "$HOME:$HOME" -e "HOME=$HOME" -w "$HOME/traceconomics" $IMAGE \
  ~/traceconomics-venv/bin/python -I -m traceconomics schedule units --out ~/.config/systemd/user
systemctl --user daemon-reload
loginctl enable-linger "$USER"                                   # timers run without a login
systemctl --user enable --now traceconomics-archive.timer        # daily at 13:00 Greek time
```

`schedule units` writes the daily timer and a `traceconomics` command in `~/.local/bin`, which runs the same container as the timer. After that:

```sh
traceconomics status                       # last runs, next release days
traceconomics release status               # every release build: result, where it is (staging, production), preview address
traceconomics release build                # by hand; the daily job does this after new data
traceconomics release promote <id> --to staging      # a build you've looked at, to the private staging address
traceconomics release promote <id> --to production   # or to the public site; no default, choose each time
traceconomics backup plan                  # archive files the cloud copy still lacks (never microdata)
systemctl --user list-timers               # when the next run is
journalctl --user -u traceconomics-archive # the job's output
```

A release build recomputes every series, runs the checks, builds and tests the site, and uploads it as a private preview; nothing reaches the public site until a person promotes it.

## Tests

```sh
python -I -m pytest
```

The tests use small saved extracts of real pages (`tests/fixtures/`) and never touch the network.

## Contributing

Ideas, questions, corrections and bug reports are welcome as [issues](https://github.com/agardelakos/traceconomics/issues). A number that looks wrong is worth an issue even if you're not sure: say which page, which series and month, and what you expected.

**Before a pull request**, open an issue for anything beyond a small fix: a change to the method, a new data source or a new dependency is discussed first. Then:

- **Run the tests.** `python -I -m pytest` for the Python package; for the site, `npm run check:code` in `site/` (type check and unit tests, what CI runs). The full `npm run check` also builds the site, which needs the data files the pipeline writes from the raw archive; the archive isn't public yet, so CI doesn't run it either.
- **Keep the outputs reproducible.** The same archive must give byte-identical files on every machine: sort every query whose rows feed an output (`ORDER BY`), write text with `\n` line endings, and write Parquet through `module1.output.parquet_connection()`.
- **Refuse surprises.** A parser that meets a file it doesn't expect raises `FormatError`; it never guesses.
- **Tests stay offline and synthetic.** Never call the network in a test. The saved extracts in `tests/fixtures/` are kept byte for byte and checked against their hashes: don't re-save or convert them. Survey microdata never go into tests or the repository; build a small synthetic survey instead.
- **Standard library first.** Code outside `src/traceconomics/local/` must not import pandas or numpy (CI installs neither). A new runtime dependency needs a reason, a pin in `pyproject.toml` and both lock files regenerated (the command is in each file's header).
- **Be gentle with the sources.** Code that fetches from ELSTAT or Eurostat makes one request at a time, with a pause.
- **The site** has every text in English and Greek (`site/src/i18n/`, `site/src/content/`); the build fails on a missing translation. If you can't write the Greek, say so in the pull request.
- **Write the reason in the code.** A comment says why a rule exists, not only what it does.

Contributions are accepted under the project's licences (Apache-2.0 for code, CC BY 4.0 for data), with no separate agreement to sign.

## Data sources

- ELSTAT, Hellenic Statistical Authority, https://www.statistics.gr. Source: ΕΛΣΤΑΤ. Reused under ELSTAT's reuse policy.
- Eurostat, https://ec.europa.eu/eurostat. Reused under Eurostat's copyright notice. Eurostat bears no responsibility for anything derived from its data here.
- Publications Office of the European Union, EU Vocabularies: the English and Greek names of the spending categories (ECOICOP version 2).

Every source, its reuse terms and how we meet them: [SOURCES.md](SOURCES.md).

## Licence

Copyright 2026 agardelakos. Code: [Apache-2.0](LICENSE), with the notices in [NOTICE](NOTICE). Data published by this project: CC BY 4.0.
