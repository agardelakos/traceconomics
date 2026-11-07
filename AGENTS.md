# AGENTS.md

Instructions for coding agents working in this repository.

## What this is

TracEconomics: an open tracker of the economy built only on public data (Greece live).
A Python pipeline (`src/traceconomics/`) archives publishers' files, rebuilds official figures and
computes new series; a static Astro site (`site/`) shows them in English and Greek.

## CONTRIBUTING.md is binding: read it first

[CONTRIBUTING.md](CONTRIBUTING.md) applies to every change you make. This file adds commands and
checks; where the two seem to differ, CONTRIBUTING.md wins and you say so in your report.

## Hard rules (one line each)

- Never edit, re-save, reformat or convert any file in `tests/fixtures/`.
- Never call the network in a test.
- Never put survey microdata in the repository, a test, a fixture or an output; use synthetic data.
- Never skip, weaken, delete or mark `xfail` a test to make a run pass.
- Never import pandas or numpy outside `src/traceconomics/local/`.
- Never add, remove or change a dependency without an agreed issue; then regenerate every lock file.
- Never make a parser guess: raise `checks.FormatError` on an unexpected file.
- Never adjust a method, tolerance or expected value to hide a difference from an official figure.
- Never change English site text without the matching Greek change in the same change.
- Never add inline scripts or resources from other sites to the site.
- Never write personal names, emails or local paths in code, comments, tests or docs.
- Never commit, push, open a pull request or change repository settings unless your human asks.

## Repository map

| Path | What it does |
|---|---|
| `src/traceconomics/cli.py` | Command line: `python -m traceconomics <command>` (`--help` on each) |
| `src/traceconomics/sources/` | One adapter per publisher (`elstat/`, `eurostat/`), their parsers, reuse-terms watch (`terms.py`); `base.py` is the polite HTTP client |
| `src/traceconomics/archive/` | Append-only raw archive (`store.py`); local-only microdata list (`local_only.py`) |
| `src/traceconomics/store/` | Observation store (DuckDB over Parquet), built from the archive, queried as of any date |
| `src/traceconomics/catalog.py`, `data/` | Reference data: parsed datasets (`datasets.toml`), country codes (`geo.toml`), mapping tables |
| `src/traceconomics/checks.py` | `FormatError` and `require()` for parsers |
| `src/traceconomics/engine/` | Arithmetic without method choices: COICOP tree, chain-linking, rates |
| `src/traceconomics/validate/` | The engine checked against official figures (V1, V1-CPI) |
| `src/traceconomics/module1/` | Inflation by household group: every option combination, outputs, checks |
| `src/traceconomics/local/` | Survey microdata code; needs the `local` extra (pandas) |
| `src/traceconomics/export/` | Files the site reads; bibliography export |
| `src/traceconomics/references/references.bib` | The bibliography every published number cites |
| `tests/` | pytest suite; `tests/fixtures/` saved publisher files; `tests/sitedata.py` made-up site data |
| `tests/selenium/` | Selenium browser suite (collected only with `--selenium`) |
| `tests/compare/` | Scripts comparing the two browser suites' results |
| `site/src/` | Pages, content (`content/<kind>/en`, `.../el`), interface text (`i18n/`), build code (`lib/`), browser code (`scripts/`) |
| `site/src/**/*.test.ts` | Vitest unit tests |
| `site/tests/ui/` | Playwright browser suite (`*.ui.ts`); `helpers.ts` is shared |
| `site/scripts/checks.mjs` | Site checks run after the build |
| `tests/catalog/` | Test catalog tooling: collect, validate, run history, wiki pages; `strict.toml` (the ratchet), `cases.toml` (the cross-suite mapping) |
| `wiki/` | The wiki's hand-written pages, copied to the GitHub wiki automatically; `tests/test_wiki_pages.py` checks the paths they name |
| `.github/workflows/` | CI (`tests.yml`), suite comparison (`compare.yml`) |

## Setup

Python 3.14, Node.js 22 or later (CI uses 24). From the repository root:

```sh
python3.14 -m venv .venv
.venv/bin/python -m pip install --require-hashes --no-deps -r requirements-dev.txt
.venv/bin/python -m pip install --no-deps --no-build-isolation -e .
cd site && npm ci
```

Install packages only into the project's virtual environment. Use `requirements-local.txt`
(microdata code) or `requirements-selenium.txt` (Selenium suite) instead of `requirements-dev.txt`
when you need them.

## Commands

```sh
.venv/bin/python -I -m pytest                                  # Python suite, offline
.venv/bin/python tests/sitedata.py site/public/data            # made-up site data (replaces site/public/data)
cd site && npm run check:code                                  # type check + unit tests, no data needed
cd site && npm run check                                       # type check, Vitest, build, site checks
cd site && npx playwright install chromium                     # once
cd site && npm run test:ui                                     # Playwright suite on the built site
cd site && npm run build                                       # build only (before Selenium)
.venv/bin/python -I -m pytest tests/selenium --selenium -n auto   # Selenium suite (Selenium lock)
```

Test cases (every test carries an ID and Given/When/Then; see the wiki's "Test management as code"):

```sh
.venv/bin/python -I tests/catalog/collect.py --out /tmp/catalog.json --no-selenium   # add --playwright/--vitest files for all suites
.venv/bin/python -I tests/catalog/validate.py /tmp/catalog.json                     # what CI's catalog job checks
```

A new or changed test gets its case in the same change. Python: the docstring (`PY-<AREA>-NNN: title`,
then Given/When/Then lines). Playwright: `test(title, gwt({ id, given, when, then }), body)`. Take the
next free number in the area; never reuse an ID, even one whose test was removed.
A new Python test file declares its layer (`pytestmark = pytest.mark.unit`, `integration` or
`repository`; definitions in `tests/conftest.py`); a test that differs overrides it with its own mark.

Host tests (headers, CSP): `npx wrangler dev --port 8788` in `site/`, then
`BASE_URL=http://127.0.0.1:8788 npm run test:ui -- --grep @smoke`, or the Selenium suite with
`--base-url http://127.0.0.1:8788`.

Lock files: after a pin change in `pyproject.toml`, regenerate `requirements-dev.txt`,
`requirements-local.txt` and `requirements-selenium.txt` with the command in each file's header.

## Conventions

Code:
- Standard library first (`urllib`, `html.parser`, `tomllib`, `smtplib`).
- Write text files with `newline="\n"`.
- Add `ORDER BY` to every query whose rows feed an output or a sum.
- Write Parquet only through `module1.output.parquet_connection()`.
- Translate a source's country codes only in `data/geo.toml`; use ISO 3166-1 alpha-2 everywhere else.
- Write the reason for a rule in a comment next to it.
- Fetching code: one request at a time, a pause between requests, `robots.txt` respected.

Tests:
- Use `tests/fixtures/` through the `fixture_bytes` fixture; add a new fixture only with its row in
  `tests/fixtures/README.md` (source URL, date, what was trimmed).
- Tests needing pandas or numpy start with `pytest.importorskip(...)`.
- Microdata tests build a small synthetic survey in the test.
- Playwright: `import { test, expect } from "./helpers"`; call `coverage.flush()` before a click
  that loads a new page.
- A change to the site's behaviour updates both browser suites.

Data handling:
- Never write to or rewrite archived files; the archive is append-only.
- Any step that publishes or copies archive files calls `archive.local_only.check()` first.
- Never read files from outside the repository unless your human points you to them.

Site:
- Every English change in `site/src/i18n/en.json` or `site/src/content/<kind>/en/` has its Greek
  twin in `el.json` or `site/src/content/<kind>/el/`.
- Every source key cited in content exists in `references.bib`.
- Ask before changing layout, navigation or wording: those need a maintainer's agreement in an issue.

## Never touch or do

- Files in `tests/fixtures/` (any change breaks `tests/test_fixtures.py` and their provenance).
- Lock files by hand; regenerate them with their header command.
- `AGENTS.md`, `CONTRIBUTING.md`, `.github/` unless the task is explicitly about them.
- Generated output (`site/dist/`, `site/coverage/`, reports) as if it were source.
- Requests to statistics offices or the live site beyond what a single reviewed run needs; no load
  or automated scanning against the website.
- Secrets: never print, log or write tokens, passwords or environment files.

## Definition of done

Run the suites that cover your change and report each result exactly as it came out.

| Change | Run |
|---|---|
| Python code or `src/traceconomics/data/` | `pytest` |
| Lock files or `pyproject.toml` | `pytest` (includes `tests/test_lock_files.py`) |
| `src/traceconomics/export/` or `tests/sitedata.py` | `pytest`, then site data, `npm run check`, `npm run test:ui` |
| Site code, content or i18n | `npm run check`, `npm run test:ui`, the Selenium suite |
| `site/public/_headers` or CSP | the host tests above, both suites |
| Browser tests only | the suite you changed, in full |

- Done means every relevant suite passed locally, or you report which failed and why.
- Report failures, skips and flaky results as they are; never retry until green and call it a pass.
- Never skip, weaken or delete a test, and never edit a fixture, to get a green run.
- If a suite can't run in your environment, say which one and why; don't claim it passed.
- List the commands you ran and their outcomes in your report and in the pull request.

## Pull requests

- One issue per pull request; no unrelated changes.
- The human who opens the pull request owns the code: they have read and understood every line,
  answer for it in review, and confirm the right to contribute it under the project's licence.
  "The AI wrote it" is never an answer in review.
- Disclose AI use and the suites run, in the pull request template's checkboxes.
- A pull request nobody stands behind is closed.
- Changes to `AGENTS.md`, `CONTRIBUTING.md` and `.github/` need a maintainer's review (CODEOWNERS),
  because this file steers every agent that reads it.
