# Test management as code

The project keeps its test cases, its traceability and its run history in the repository, next to
the tests, instead of in a separate test-management tool. This page explains how, and compares
the approach honestly with a dedicated tool.

## Test cases live on the tests

Every automated test carries its case: a stable ID, a title, and Given/When/Then lines.

| Suite      | ID prefix        | Where the case is written                                          |
| ---------- | ---------------- | ------------------------------------------------------------------ |
| pytest     | `PY-<AREA>-NNN`  | the test's docstring: `PY-<AREA>-NNN: title`, then Given/When/Then |
| Selenium   | `SEL-<AREA>-NNN` | the test's docstring, same form                                    |
| Playwright | `PW-<AREA>-NNN`  | the test's annotations                                             |
| Vitest     | `VT-<AREA>-NNN`  | the test's annotations                                             |

Rules:

- **A parametrized test is one Scenario Outline**: one ID, with the parameters as its examples.
- **An ID is never reused.** When a test is removed, its case is listed as obsolete, with the last
  commit it existed at, so a past run can always be read against the case it ran.
- **Defect links** go on the test: `xfail`, `test.fail` and skip reasons carry `#<issue>`.
- **A check in CI** refuses a case without an ID or without Given/When/Then, in every suite.

A catalog of all cases is generated from the tests by the tooling in `tests/catalog/`: `collect.py`
reads the four suites (pytest and Selenium through a collection plugin, Playwright from its test
listing, Vitest from a run's report), `validate.py` is the CI check, `history.py` keeps the run
records and `wiki.py` writes the `Tests` pages. `tests/catalog/strict.toml` sets how strict the
check is: since every test has its case, it applies to all files (`all = true`), and a Playwright or
Selenium case missing from the cross-suite mapping is an error too.

## Two browser suites, one mapping

The site has two browser suites, Playwright and Selenium, so the two tools can be compared on the
same product. **Each suite carries only its own IDs and text.** The cross-suite link is a separate
file, `tests/catalog/cases.toml`, mapping a shared case `TC-<AREA>-NNN` to the Playwright and
Selenium IDs that implement it, or saying why a case is in one suite only. This gives traceability
("which behaviours are covered by both suites, which by one") in one place, without either suite
having to name the other.

## Run history

Every suite run on `main`, and every release run, is recorded against its commit or build:
trigger, commit, build ID, environment, per-case result, duration and retries. Release runs count:
the full browser suite before upload, the smoke set on the uploaded preview and the check after a
promote are the runs that actually gate production, on real data. Release runs are labelled by build
and platform (for example "release build, Linux Arm").

Records are appended to the branch `test-history`, keeping the last 200 runs per trigger (a
working assumption, to be revisited with real volumes). Pull-request runs are not recorded: they
test code that may never merge.

## Generated wiki pages

The wiki's `Tests-*` pages are generated from the catalog and the run history: the cases by
suite and area, obsolete cases, the last runs per case, and each case's flakiness rate. They are
never edited by hand; a correction goes into the test, and the page follows. Links to them appear in
the sidebar as they are published.

## Compared with a dedicated test-management tool

The comparison is with a typical case-management tool of the TestRail kind: a database of cases,
plans, runs and results with its own web interface.

### Strengths

- **Cases can't drift from the code.** The case text sits on the test that implements it. Changing
  the behaviour means editing the same file; a stale case is visible in the diff.
- **Reviewed in the same pull request.** A new or changed case is reviewed with the code and the
  assertion, by the same people, under the same rules (CODEOWNERS, required checks).
- **Versioned with the code.** Any commit shows exactly which cases existed and what they said.
  Branches carry their own cases; nothing to synchronise on merge.
- **History per commit and per build.** Every recorded run points at an exact commit or release
  build, so a result is always reproducible against the code it ran on.
- **Enforced, not requested.** CI refuses a test without a case, so coverage of the catalog is a
  gate, not a habit.
- **Works with any framework, old or new.** A docstring or an annotation is all a framework needs;
  nothing to integrate, no plugin to keep alive.
- **Free and open.** No licence, no seats, no vendor account; anyone who forks the repository gets
  the whole system.
- **Independent suites stay independent.** The mapping file links two suites without either one
  depending on the other, which a single shared case record in a tool tends to blur.

### Weaknesses

- **No manual execution recording.** There is no interface for a tester to step through a manual
  case and record a result; manual and exploratory testing is out of scope for now (see
  [Future](Future)).
- **No test plans or milestones interface.** Planning which cases run for which release is done in
  code and CI configuration, not in a planning screen.
- **Non-technical stakeholders depend on the generated pages.** Anyone who doesn't read code sees
  cases only through the wiki, which is read-only and only as current as the last generation.
- **Reporting is only what we build.** No ready-made dashboards, trend charts or custom queries;
  every report is code to write and maintain.
- **No assignment or workflow.** No owners per case, no review states, no notifications beyond
  what GitHub issues and pull requests give.
- **Case text is constrained by the code.** Long preconditions, attachments or screenshots don't fit
  well in a docstring or annotation.
- **History lives in git.** A branch of run records works at this scale; at much larger volumes a
  database would query better.

For a small, code-first project with automated suites and a public repository, the strengths
outweigh the weaknesses. A team with large manual regression packs or non-technical test owners
would weigh them differently.

---

_This page is kept in the repository, in [`wiki/Test-management-as-code.md`](https://github.com/agardelakos/traceconomics/blob/main/wiki/Test-management-as-code.md), and copied here automatically. Changes go through a pull request; an edit made here is replaced at the next update._
