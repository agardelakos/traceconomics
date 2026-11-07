# Test strategy

What each layer of testing proves, where it runs, and what is deliberately left out. Commands are
in [CONTRIBUTING.md](https://github.com/agardelakos/traceconomics/blob/main/CONTRIBUTING.md).

## Risks the strategy is built around

1. **A wrong number published.** Arithmetic, method or parsing errors that produce plausible but
   wrong series.
2. **A publisher's file read wrongly.** Layouts change without notice; a silent misread is worse
   than a crash.
3. **Non-reproducible outputs.** The same archive must give the same bytes on every machine.
4. **A broken or inaccessible site.** Interactive parts that fail, pages that break the Content
   Security Policy, accessibility regressions, privacy promises not kept.
5. **Microdata leaking.** Survey microdata must never reach a published file, a sync or a test.

## Layers

| Layer | Tooling | Runs on | Proves |
|---|---|---|---|
| Unit and integration | pytest | every push and pull request | parsers, archive, store, engine, method code, export, release logic behave as specified |
| Microdata code | pytest with the optional `local` extra (separate job) | every push and pull request | groups, income bands, bootstrap standard errors, code mapping and the survey reader, on synthetic surveys |
| Fixture integrity | pytest (`tests/test_fixtures.py`) | every push and pull request | untouched publisher files are byte-identical to what was served |
| Dependency integrity | pytest (`tests/test_lock_files.py`) | every push and pull request | every hashed lock file agrees with the pins in `pyproject.toml` |
| Site unit tests | Vitest | every push and pull request; release builds | formatting, topics, i18n parity, structured data, the calculator engine and its parity with the published series |
| Site checks | `site/scripts/checks.mjs` | every push and pull request; release builds | translations complete, sources resolvable, no inline scripts or third-party resources, page budgets, internal links, sitemap and canonical addresses |
| Browser (primary) | Playwright, Chromium | every push and pull request; release `ui-test` and `smoke` | every interactive part works in both languages; accessibility; CSP and headers; privacy |
| Browser (second suite) | Selenium, Chrome for Testing | every push and pull request (not required); on demand for comparison | the same behaviour, independently written, as a cross-check of the primary suite and of the tools |
| Validation against official figures | `traceconomics check …` | release builds; by hand | the engine and the method rebuild official figures within stated margins |

### pytest

Unit and integration tests for the Python package. Tests run **offline**: parsers are exercised on
trimmed copies of real publisher files in `tests/fixtures/`, each with its source URL, retrieval
date and what was trimmed recorded in `tests/fixtures/README.md`. Failure paths are tested as well
as happy paths: a changed layout must raise `FormatError`.

Untouched fixtures are stored byte for byte (`.gitattributes` disables line-ending conversion) and
checked against their published SHA-256, so they stay evidence of what the publisher served, not a
local approximation of it.

Microdata code is tested on **synthetic surveys** built in the test, never on real microdata. Those
tests need the optional `local` extra and skip themselves without it (`pytest.importorskip`). CI
runs them in a job of their own, with the extra installed, while the main pytest job deliberately
installs neither pandas nor numpy: one job proves the microdata code works, the other that code
outside `local/` doesn't depend on them. The local-only rule has its own tests: every publishing or syncing step
must refuse microdata datasets.

### Vitest

Unit tests for the site's build-time and browser code. The calculator parity test asserts that the
in-browser calculator, left at a preset, reproduces the pipeline's published series to the last
digit: the one computation the browser does is checked against the one Python did.

### Playwright

The primary browser suite (`site/tests/ui/*.ui.ts`), on Playwright's own Chromium. It drives every
interactive part (Explore, the calculator, the group finder, the income panel, menus, the theme
switch, glossary terms) in English and Greek, and covers:

- **Accessibility**: axe-core on every kind of page, phone and desktop widths, light and dark
  themes, each menu open once; WCAG 2.2 AA rules; any serious or critical violation fails.
- **Security headers and CSP** (`host.ui.ts`), against a server that applies the site's headers
  (locally `wrangler dev`, in a release the uploaded preview).
- **Privacy**: the calculator and finder send and store nothing a reader enters; the theme choice is
  the only value kept; pages request nothing from other sites.
- **No-script**: pages remain usable without JavaScript.
- **Links**: every page and link in the sitemap.

Expected values come from the data and language files, not from literals, so the suite runs on any
valid data set. No retries (`retries: 0`) and `forbidOnly`: a test that passes only on a second try
is a defect. A failure keeps a screenshot and a trace.

### Selenium

A second browser suite (`tests/selenium/`), in Python and Selenium on a pinned Chrome for Testing,
over the same areas. It exists to compare the two tools on the same product and to cross-check the
primary suite: a defect one suite misses and the other catches says something about the test, not
only the code. The two suites were first written independently. Each carries only its own code and
case IDs; a separate mapping file links them (see [Test management as code](Test-management-as-code)). `tests/compare/compare.py` runs both several
times on the same build and reports wall time, failures and flaky tests; a hand-started workflow
does the same on CI.

### Validation against official figures

These are not unit tests; they are checks on real data, run in every release build and by hand:

- `check v1`, `check v1-cpi`: the engine rebuilds the official all-items indices from their
  published sub-indices and weights, within the margin the rounding of the inputs allows.
- `check v2`: the survey microdata rebuild the published household spending figures (local only).
- `check mapping`: old spending codes mapped to the current classification, against the next year.
- `check combos`: every option combination; identities that must hold, and how much each option
  moves the result.
- Further checks compare our series with official figures and with other studies' published
  series, rebuilt with their own settings.

Margins are fixed in advance, in three tiers: official series exact at one decimal; a study
reproduced with its own settings within a stated target and limit; a study with different settings
reported and explained, with no pass or fail. A difference is shown and explained, never tuned
away.

## Test data for the site

The site's build and browser tests need a full data folder, which the real pipeline writes from the
archive and microdata. In CI, `tests/sitedata.py` writes **made-up data through the real export
code**: fixed made-up prices and baskets go through the real series code, output writer and site
export, so the files have exactly the production format. The numbers mean nothing, and are
deterministic. Release builds run the same suites on the real data.

## Quality gates

| Gate | Where | Blocks |
|---|---|---|
| Required checks `python`, `site`, code scanning | pull requests to `main` | merging |
| Coverage of the site's own code (Vitest and Playwright merged) | `site` job | fails below 90%, or if any file of the site's code is loaded by no test |
| Lock files agree with pins | `python` job | merging |
| Release checks (`check-v1`, `check-v1-cpi`, `check-combos`, `site-check`) | release build | the build |
| `ui-test`: the full Playwright suite on the built files, before upload | release build | the upload |
| `smoke`: the `@smoke` set on the uploaded preview, with the host's real headers | release build | promotion |
| Promote check: the target address serves the promoted build's own files | after every promote | reported |

A build held back by its browser tests can be retested on the same files (`release retest`), which
refuses if the tests changed: a wrong test or page needs a new build. Promotion is always a
person's decision.

The Selenium and comparison jobs run on every push and pull request but are not required checks:
they inform, they don't gate.

## Deliberately not tested

- **Other browser engines.** Both suites run Chromium-based browsers only. The site uses plain
  modern HTML and CSS with little script; Firefox and WebKit are not in the matrix.
- **Visual regression.** No screenshot comparison; layout is checked through accessibility, page
  budgets and behaviour.
- **Live publishers in CI.** Fetching code is tested on saved files. A real format change is caught
  at run time by the format checks, which stop the run, not by CI.
- **Real microdata in CI.** The microdata path is tested on synthetic surveys; its checks against
  published figures (`check v2`) run only where the microdata are held.
- **Load and performance.** The site is static files; page weight is bounded by the build's budgets
  instead.
- **Translation quality.** Tests check that every text exists in both languages, not that the Greek
  is good; that is a native speaker's review.
- **Manual and exploratory testing** has no recorded cases yet (see [Future](Future)).

---

*This page is kept in the repository, in [`wiki/Test-strategy.md`](https://github.com/agardelakos/traceconomics/blob/main/wiki/Test-strategy.md), and copied here automatically. Changes go through a pull request; an edit made here is replaced at the next update.*
