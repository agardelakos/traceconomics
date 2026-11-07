# Future

Expansions that are deliberately left for later. Nothing on this page is built or scheduled.

## Manual and exploratory test cases

Today every recorded test case is automated (see
[Test management as code](Test-management-as-code)). Manual and exploratory testing is out of
scope for now. When it is added, the plan is to keep it in the same system rather than a separate
tool:

- **Cases with stable IDs** of the form `MAN-<AREA>-NNN`, with a title and Given/When/Then steps,
  kept in the repository next to the automated cases and collected into the same catalog. As with
  the automated cases, an ID is never reused.
- **Execution recorded through an issue form**: a tester opens an issue from a template, names the
  case, the build or address tested, the browser and device, the result and any evidence. The
  issue is the run record, linked to the case; a failure links to the defect issue.
- **Exploratory sessions** recorded the same way: a charter, the time spent, what was covered and
  what was found.
- The generated `Tests-*` pages would then show manual results next to automated ones.

## A query API

Data are published as static files. A queryable API may come much later; the storage and output
layout are designed so it can be added without a rewrite.

## A release archive

Each release's full set of output files, deposited in a public long-term archive, so a cited
release stays available with its own identifier.

---

*This page is kept in the repository, in [`wiki/Future.md`](https://github.com/agardelakos/traceconomics/blob/main/wiki/Future.md), and copied here automatically. Changes go through a pull request; an edit made here is replaced at the next update.*
