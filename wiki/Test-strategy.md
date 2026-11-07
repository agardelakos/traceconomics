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

Every test names its layer with a mark, once per file (`pytestmark = pytest.mark.unit`), and a test
that differs from its file overrides it with its own mark (`tests/conftest.py`):

- **unit**: one of our components on its own; it may use its own files in a temporary folder, its
  collaborators are faked or absent;
- **integration**: two or more of our components meeting through a real resource: an archive on
  disk, the observation store, the run job, the series read by the site export;
- **repository**: checks on the repository's own files (fixtures, lock files, wiki pages, the test
  tooling); no package code runs.

A test file without a layer stops the run before any test: the choice is the author's, never a
default. The layer is a tag on each test case in the [test pages](Tests).

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

A second browser suite (`tests/selenium/`), written independently in Python and Selenium on a
pinned Chrome for Testing, over the same areas. It exists to compare the two tools on the same
product and to cross-check the primary suite: a defect one suite misses and the other catches says
something about the test, not only the code. The suites are kept **blind to each other**: neither
references the other's code or case IDs; only a separate mapping file links them (see
[Test management as code](Test-management-as-code)). `tests/compare/compare.py` runs both several
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

## Coverage

Two figures, one per codebase, each split by the layer of test that reaches the code:

| Badge | Code | Layers | Measured by |
|---|---|---|---|
| back-end coverage | the Python package (`src/traceconomics`) | unit, integration | coverage.py, in both pytest jobs, combined |
| front-end coverage | the site's own code (`site/src/scripts`, `site/src/lib`, the pages' scripts) | unit, integration, e2e | V8 coverage from Vitest and Playwright, merged |

Both count **lines**: of the lines that hold code, the share run by at least one test. A line run by
tests of several layers counts once, for the **lowest** of them: unit, then integration, then
end-to-end. So the parts read as "what the unit tests reach", "what the integration tests add" and
"what only the browser reaches", and they always add up to the total. The total is rounded down to a
tenth; the parts share it by largest remainder.

- **Back-end**: `tests/conftest.py` labels every line coverage.py records with the layer of the test
  running it (a dynamic context), including the lines run when a test file is imported. A covered
  line without a layer, or one run by a `repository` test, fails the split rather than being
  guessed. Branch coverage is recorded too, and shown in the HTML report, not on the badge.
- **Front-end**: Vitest runs twice in CI, the unit tests alone, then all of them; a line the second
  run covers but not the first is one only the integration tests reach (the tests that need the
  generated data files: the calculator parity test and the data-file checks). A line only the
  browser tests ran is end-to-end.
- **Not measured**: the Selenium suite (it tests the same pages as Playwright, through another
  tool) and the release checks on real data.

Both totals take the same colours: red below 90%, yellow from 90%, green from 95%. The site's figure
fails its build below 90%. The Python figure aims at the same 90% but was first measured at 73.9%,
so its run fails below a **ratchet** instead (`RATCHET` in `tests/coverage/overview.py`): set from
that baseline, raised as tests are added, never lowered to pass a run, until it reaches 90%.

CI's `coverage` job writes the split on the run's page and keeps the Python HTML report (artifact
`python-coverage`, each line showing the layers that ran it; the site's is `site-coverage`); on
`main`, the `badges` job publishes both badges. Locally: `python -I -m coverage run -m pytest`, then
`python -I -m coverage html`; the site's commands are in the README.

## Quality gates

| Gate | Where | Blocks |
|---|---|---|
| Required checks `python`, `site`, code scanning | pull requests to `main` | merging |
| Coverage of the site's own code (Vitest and Playwright merged) | `site` job | fails below 90%, or if any file of the site's code is loaded by no test |
| Coverage of the Python package | `coverage` job | fails below a ratchet that only rises (73% from the first measurement, 73.9%) towards the site's 90% floor; fails if a covered line has a wrong or missing layer |
| Every test has a layer | pytest collection | the run |
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
