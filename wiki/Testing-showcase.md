# Testing showcase

The repository holds two kinds of testing. The **core** is what TracEconomics needs: pytest,
Vitest, the Playwright browser suite, the test catalog (an ID and Given/When/Then on every test),
formatting and linting, the code scan, and the code's own documentation. Contributors keep the core
green; it is described in the [Test strategy](Test-strategy).

The **testing showcase** is the rest: work the maintainer does as a software-testing portfolio, on
a real product rather than a demo. It is kept apart on purpose, and **asks nothing of
contributors**:

- a contributor never has to write, update or run a showcase test;
- a change that breaks a showcase suite is fine: the maintainer follows up;
- no showcase job is a required check on a pull request or a step of a release build;
- each showcase tool has its own lock file (`requirements-selenium.txt`,
  `requirements-mutation.txt`), never a dependency of the core.

Contributions to the showcase are welcome, never required.

## What is in it

| Part                    | Where                                                                   | Its page                                     |
| ----------------------- | ----------------------------------------------------------------------- | -------------------------------------------- |
| A second browser suite  | `tests/selenium/` (Python, Selenium, Chrome for Testing)                | [Selenium cases](Tests-Selenium)             |
| The two suites compared | `tests/compare/`                                                        | the run's page; the comparison artifact      |
| The code map            | `tests/coverage/code_map.py`, `tests/catalog/code_charts.py`            | [Code](Code#the-map), [Code-site](Code-site) |
| Mutation testing        | `tests/coverage/mutation.py`, `tests/coverage/mutation-equivalent.toml` | [Mutation testing](Tests-Mutation)           |
| Run history             | `tests/catalog/history.py`, `tests/catalog/vm_pull.py`                  | [Runs](Tests-Runs)                           |

## How it runs

All of it runs in the `showcase` workflow (`.github/workflows/showcase.yml`):

- **After every pipeline run on `main`:** the Selenium suite on the made-up data, in every data
  state the pipeline tests Playwright on; one comparison of that run's Playwright results with
  Selenium's; the code map, from the pipeline's coverage data and Selenium's; the run's record on
  the branch `test-history`; and the wiki.
- **Weekly:** the Selenium suite on `main`, so a change outside the repository (a new Chrome for
  Testing, a dependency) shows even in a quiet week.
- **By hand:** the long comparison (several runs of each suite) and mutation testing.

Pull requests don't run it. Its status is the `showcase` badge in the README. Because nobody else
keeps Selenium in step with the site, the [Selenium cases](Tests-Selenium) page and the
[test overview](Tests) say whether it is: whether the newest recorded run on `main` has Selenium's
results, and which Playwright cases the cross-suite mapping doesn't list yet.

## The Selenium suite

A second browser suite (`tests/selenium/`), in Python and Selenium on a pinned Chrome for Testing,
over the same areas as Playwright. It exists to compare the two tools on the same product and to
cross-check the primary suite: a defect one suite misses and the other catches says something about
the test, not only the code. The two suites were first written independently. Each carries only its
own code and case IDs; a separate mapping file, `tests/catalog/cases.toml`, links them (see
[Test management as code](Test-management-as-code)). The maintainer keeps that mapping: a new
Playwright case without its entry is only a warning in the catalog check.

Running it locally, after `npm run build` in `site/`, with `requirements-selenium.txt` installed:

```sh
.venv/bin/python -I -m pytest tests/selenium --selenium -n auto
```

The plain pytest run never collects these. The tests marked `host` need a server that applies the
site's headers: `npx wrangler dev --port 8788` in `site/`, then add
`--base-url http://127.0.0.1:8788`.

## The two suites compared

`tests/compare/compare.py` runs both suites several times on the same build and reports wall time,
failures and flaky tests; the `showcase` workflow's hand-started run does the same on CI, with every
mode (both suites spread over all workers, by file, one test at a time). After every pipeline run on
`main`, a shorter report puts that one run's results side by side on the run's page
(`tests/compare/report.py`).

## The code map

The `Code-*` pages, the [code reference](Code), are core documentation: each package's modules,
their docstrings and public parts. The code map adds what the tests run, from the last coverage run
on `main` (`tests/coverage/code_map.py`, stored on the branch `test-history`). Each module lists its
lines by the lowest layer of test that runs them, the lines no test runs, and the test cases that
run it, each linked to its steps on the `Tests-pytest` page. Each public function shows how many
tests run it, or "imported only" (defined while a test file was loaded, but never called by a test),
or "no test". The overview lists the `repository` tests, which check the repository's own files and
run no package code, and any test run without a case. A test that runs a line doesn't always check
it.

The map covers the site's own code too, on the `Code-site` page: each file's lines by the layer
that runs them (Vitest's unit and integration files, then Playwright), and the Vitest files,
Playwright cases and Selenium tests that run it. Vitest is measured per test file, Playwright per
case, Selenium per test (through Chrome's DevTools protocol, taken before every navigation and
click). The overview draws it all as charts, each in a light and a dark version with its numbers in
a table below: stacked bars of each area's lines by status, heatmaps of the share each suite runs,
and a table of the lines only Playwright or only Selenium runs. Each line's status is the coverage
badges' own; which tests run a line comes from each test's own coverage, kept to what the merged
runs and the build's bundles confirm, so the two browser suites are compared the same way.

## Mutation testing

The [mutation testing](Tests-Mutation) page shows how well the tests check the engine, not only what
they run: mutation testing with [mutmut](https://github.com/boxed/mutmut), started by hand.
mutmut changes the engine's code in small ways, one at a time, and runs the tests the code map says
run the engine on each change. The page gives the share of changes some test noticed, the score of
every run so far, the result per function, and every change none did: a gap in the tests to close
with a test, or a change that behaves the same as the code, listed with its reason in
`tests/coverage/mutation-equivalent.toml`. `Code-engine` ends with the newest score and a link.

## Run history

Every run of the suites on `main`, and every release build's browser tests, recorded against its
commit or build: how it works is in [Test management as code](Test-management-as-code#run-history);
the recent runs are on [Runs](Tests-Runs), and each case's last results and flakiness on its suite's
page.

---

_This page is kept in the repository, in [`wiki/Testing-showcase.md`](https://github.com/agardelakos/traceconomics/blob/main/wiki/Testing-showcase.md), and copied here automatically. Changes go through a pull request; an edit made here is replaced at the next update._
