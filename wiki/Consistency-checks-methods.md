# Consistency checks methods

How the second topic, the consistency of official figures, checks whether the official figures add
up. This page is for contributors and reviewers: what is computed, where, and what tests it. The
economics, for readers, is on the site's
[method page](https://traceconomics.com/en/gr/official-figures-consistency/method/), which explains
each check.

## What is checked

The code is `src/traceconomics/module5/`, run in every release build as the step `consistency`:

- **A published rate against its own index** (`module5/cpi.py`): the Greek CPI's rates, checked
  against the index they come from, and against our rebuild.
- **Official indices rebuilt from their own parts** (`module5/rebuilds.py`): the CPI from ELSTAT's
  item indices and weights, the HICP from Eurostat's.
- **The household budget survey against the office's own tables** (`module5/hbs.py`): our household
  types and the spending by item, against ELSTAT's own variables and tables, and against other
  surveys.
- **"Same question, different sources"** (`module5/questions.py`): renters, rent paid, household
  income and unemployment, as each source answers them.

Each check's result (`module5/record.py`) holds every period compared, how often the two sides
agree, and why they differ.

## A difference is explained, never called an error

A difference never fails a build. Rounding is labelled by the code; every other explanation is
written by hand, with its evidence, in `src/traceconomics/data/m5_explanations.toml`, and until then
the difference reads "not known yet".

## Where it is tested

Tests PY-M5-001 to PY-M5-019, in `tests/test_module5.py`.
