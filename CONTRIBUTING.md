# Contributing to TracEconomics

Thank you for looking. TracEconomics is an open tracker of the economy built only on public data:
it keeps every published version of its source files, rebuilds official figures from their parts,
and publishes numbers that don't otherwise exist, each traced to its source and explained in plain
language. Greece is live; more topics and countries are planned.

This file is binding for every contribution, by a person or with the help of a tool. The longer
pages (architecture, design principles, adding a source, test strategy) are in the
[wiki](https://github.com/agardelakos/traceconomics/wiki). The wiki's pages are kept in
[`wiki/`](wiki/) and copied to the wiki automatically: to change one, send a pull request.

Everyone taking part in the project follows the [code of conduct](CODE_OF_CONDUCT.md).

## What is welcome

- **Bug reports.** A number that looks wrong is worth an issue even if you're not sure. Say which
  page, which series and month, and what you expected.
- **Corrections about a data source**: a changed file layout, a broken link, reuse terms we have
  wrong, a better or lower-level source for something we compute.
- **Tests**: a missing case, a weak assertion, a flaky test with evidence.
- **Accessibility**: anything that makes the site harder to use with a keyboard, a screen reader,
  zoom or a small screen.
- **Translations**, reviewed by a native speaker. The site is built in English and Greek; the Greek
  version is offered once a native speaker has reviewed it.
- **A new country**, only after an issue. The design allows it without a redesign, but each
  country's sources, terms and method choices are checked on paper first.

## How to contribute

1. **Open an issue first**, from one of the
   [issue forms](https://github.com/agardelakos/traceconomics/issues/new/choose), for anything
   beyond a small fix (a typo, an obvious bug with a one-line fix). A change to the method, a new
   data source, a new dependency or a new feature is discussed before any code is written.
2. **Layout, navigation and wording changes need a maintainer's agreement first, in an issue.** The
   pages are ordered for a first-time, non-expert reader, following design decisions that aren't
   all written down in public, so a well-meant rearrangement may be declined.
3. **One issue per pull request**, and nothing unrelated in it: no drive-by reformatting, renames
   or dependency bumps.
4. Fill in the pull request template. It asks what you tested and how, and whether AI tools were
   used.
5. CI must pass. The required checks are the Python tests (`python`), the site's checks and browser
   tests (`site`) and code scanning.

## Hard rules, and why

These protect what the project promises: every number traceable, reproducible and honest.

- **Never edit, re-save or convert a file in `tests/fixtures/`.** They are copies of publishers'
  files; the untouched ones are stored byte for byte (`.gitattributes`) and checked against their
  published hashes (`tests/test_fixtures.py`), so anyone can download the original and compare. A
  new fixture comes with its source URL, retrieval date and what was trimmed, in
  `tests/fixtures/README.md`.
- **No network in tests.** Tests must give the same answer offline, every time, and must never send
  traffic to a statistics office.
- **Survey microdata never go into the repository, a test, a published file or a sync.** Their access
  terms don't allow redistribution. Tests use small synthetic surveys. Any step that publishes or copies archive files
  calls `archive.local_only.check()` first.
- **Parsers refuse surprises.** A file that doesn't look as expected raises `FormatError`; it is
  never guessed at. A changed layout is a reason to look, not to carry on with numbers that may be
  wrong.
- **Outputs are byte-identical on every machine.** Sort every query whose rows feed an output
  (`ORDER BY`), write text with `\n` line endings, and write Parquet through
  `module1.output.parquet_connection()`. The same archive must give the same files on x86 and Arm.
- **Standard library first.** Code outside `src/traceconomics/local/` must not import pandas or
  numpy; CI installs neither. A new runtime dependency needs an issue, an exact pin in
  `pyproject.toml` and every lock file regenerated (the command is in each file's header;
  `tests/test_lock_files.py` fails if they drift).
- **Be gentle with the sources.** Code that fetches makes one request at a time, with a pause, a
  User-Agent naming the project, and respects `robots.txt`.
- **The raw archive is append-only.** Files are kept exactly as received and never changed or
  deleted; everything after it can be rebuilt from it.
- **Show differences; never tune them away.** A gap between our figure and an official one is shown
  and explained. Never adjust a method, a tolerance or a test to make it disappear.
- **Every published number cites its method sources.** The build fails on a missing one. A
  bibliography entry (`src/traceconomics/references/references.bib`) is copied from the document or
  its verified record, never written from memory; what can't be confirmed is left out.
- **Every English text on the site is also changed in Greek, in the same pull request**
  (`site/src/i18n/`, `site/src/content/`). The build fails on a missing translation. If you can't
  write the Greek, say so in the pull request.
- **The site loads nothing from other sites and runs no inline scripts.** The Content Security
  Policy and the site checks enforce this; the only exception is the cookieless visit counter in
  release builds.
- **Country codes are ISO 3166-1 alpha-2** in every ID, path and URL. A source's own codes are
  translated once, at the boundary (`src/traceconomics/data/geo.toml`).
- **Never skip, weaken or delete a test to get a green run.** Report a failure as it is.
- **Code stands on its own.** Comments say why a rule exists, not only what it does. Code, comments
  and tests contain no personal names, emails or local paths.

## Setting up

Python 3.14 and, for the site, Node.js 22 or later (CI uses 24).

```sh
python3.14 -m venv .venv
.venv/bin/python -m pip install --require-hashes --no-deps -r requirements-dev.txt
.venv/bin/python -m pip install --no-deps --no-build-isolation -e .
```

The lock files pin every package and check it against its hash. `requirements-local.txt` adds the
optional microdata code (pandas); `requirements-selenium.txt` adds the Selenium browser tests.

## Running the tests

**Python** (from the repository root):

```sh
.venv/bin/python -I -m pytest
```

Tests that need the optional `local` extra skip themselves without it (`pytest.importorskip`).

Every test file names its layer, `unit`, `integration` or `repository`, once
(`pytestmark = pytest.mark.unit`); `tests/conftest.py` says what each means, and a file without one
stops the run. For coverage, `.venv/bin/python -I -m coverage run -m pytest`, then
`.venv/bin/python -I -m coverage html` (split by layer: the wiki's Test strategy, "Coverage").

**The site** needs data files, which the pipeline writes from the raw archive. Made-up data in the
same format, written through the real export code, will do:

```sh
.venv/bin/python tests/sitedata.py site/public/data   # replaces whatever is in site/public/data
cd site
npm ci
npm run check            # type check, unit tests (Vitest), build, site checks
npx playwright install chromium   # once
npm run test:ui          # browser tests on the built site (Playwright), accessibility included
```

`npm run check:code` is the quick check that needs no data (type check and the unit tests that
don't read data files).

**Selenium**, the second browser suite, after `npm run build` in `site/`, with the Selenium lock
installed:

```sh
.venv/bin/python -I -m pytest tests/selenium --selenium -n auto
```

The plain pytest run never collects these. The tests marked `host` need a server that applies the
site's headers: run `npx wrangler dev --port 8788` in `site/` and add
`--base-url http://127.0.0.1:8788`.

Writing a browser test: in Playwright, import `test` from `site/tests/ui/helpers.ts`, not from
`@playwright/test`, and call `coverage.flush()` before a click that loads a new page. A change to
the site's behaviour updates both browser suites.

## Licences

- Code: [Apache-2.0](LICENSE), with the notices in [NOTICE](NOTICE).
- Data published by the project: CC BY 4.0.
- Contributions come in under the same licences they go out under (inbound = outbound). There is
  no contributor licence agreement to sign. By opening a pull request you confirm you have the
  right to contribute its contents under these licences.

## AI-assisted contributions

AI-assisted contributions are welcome. The human who opens a pull request owns the code in it:

- they submit it, have read and understood every line, and answer for it in review;
- they confirm they have the right to contribute it under the project's licence;
- "The AI wrote it" is never an answer in review.

The pull request says whether AI was used, for which parts, and that the relevant test suites were
run locally (the template's checkboxes). A pull request nobody stands behind is closed.

Instructions for coding agents are in [AGENTS.md](AGENTS.md). Changes to `AGENTS.md`,
`CONTRIBUTING.md` and anything under `.github/` need a maintainer's review (`.github/CODEOWNERS`),
because these files steer every contributor and every agent that reads them.

## Security

Don't open a public issue for a security problem. Report it privately through the repository's
**Security** tab, **Report a vulnerability**. Details in [SECURITY.md](SECURITY.md).

## More

- [The wiki](https://github.com/agardelakos/traceconomics/wiki): architecture, design principles,
  adding a source or country, test strategy.
- [README.md](README.md): what the project does and every command.
- [SOURCES.md](SOURCES.md): every source, its reuse terms and how we meet them.
- [src/traceconomics/README.md](src/traceconomics/README.md) and [site/README.md](site/README.md):
  where things are in the code.
