# Comparing the browser suites (testing showcase)

Scripts that compare the Playwright and Selenium suites on the same build of made-up data: part of
the maintainer's testing showcase, never required of a change.

- `compare.py` runs both suites several times and reports wall time, failures and flaky tests (the
  `showcase` workflow's hand-started run).
- `report.py` writes one run's results, or both suites side by side, on a CI run's page.

More on the wiki, "Testing showcase".
