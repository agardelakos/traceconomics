# The traceconomics package

The pipeline behind the website: it keeps every source file, reads them into a store, computes the
series and writes the files the site reads. Installing it and the commands are in the
[root README](../../README.md); the website itself is in [site/](../../site/README.md).

## How data flows

```
publishers' files ─► archive ─► store ─► module 1 ─► outputs ─► export ─► site/public/data
 (ELSTAT, Eurostat)  (raw, kept   (every    (indices,    (Parquet,   (small JSON
                      for good)   parsed     rates,       CSV)        and CSV files)
                                  value)     contributions)
                         ▲
 survey microdata ─► local ─► weights tables (archived as oet-local)
 (owner's machines only)
```

- **The archive** is the only thing that can't be rebuilt. Every file is kept exactly as received,
  with a manifest, and never overwritten or deleted.
- **The store** is a cache: delete it and `store rebuild` gives it back from the archive.
- **Everything after the store** is rebuilt from it, byte for byte on any machine.
- **Microdata** (the household budget survey's public use files) are read only by `local/`, in
  memory, on the owner's machines. Only their aggregates (spending shares by group) go back into the
  archive, and from there into the series.

## Where things are

| Path | What it holds |
|---|---|
| `cli.py`, `__main__.py` | The command line: `python -m traceconomics <command>` |
| `config.py` | User settings, from a TOML file outside the repository (see `config.example.toml`) |
| `job.py` | The daily job: is a release due, fetch, report; then the follow-up steps below |
| `sources/` | One adapter per publisher: how its files are found and fetched (`elstat/`, `eurostat/`), their parsers, and the reuse-terms watch (`terms.py`). `base.py` is the polite HTTP client they share |
| `archive/` | The append-only raw archive (`store.py`; layout in its docstring) and the list of microdata datasets that must never leave the owner's machines (`local_only.py`) |
| `store/` | The observation store (DuckDB): built from the archive (`build.py`), queried as of any date (`query.py`) |
| `catalog.py`, `data/` | Reference data: which datasets are parsed and how, country codes, mapping tables, published figures used in checks. Each file says what it is in its header |
| `checks.py` | `FormatError`: parsers refuse a file that doesn't look as expected |
| `engine/` | The arithmetic, with no method choices: the COICOP tree, chain-linking at December, rates |
| `validate/` | The engine checked against official figures (V1: the HICP from Eurostat's parts; V1-CPI: the Greek CPI from ELSTAT's) |
| `module1/` | Inflation by household group: weights timing, prices, indices, rates, contributions, every option combination, and their checks |
| `local/` | Reads the survey microdata: household groups, spending shares, standard errors, error bands, the mapping of old codes to COICOP 2018. Needs the `local` extra (pandas) |
| `export/` | The published files: the site's data, the calculator's inputs, category names, the bibliography |
| `references/` | The bibliography (`references.bib`) every published number cites |
| `release.py` | A release: recompute, check, build the site, upload a private preview; a person promotes it |
| `notify.py`, `heartbeat.py` | Reports by email (or a file), and a heartbeat after every run |
| `backup.py`, `analytics.py` | Copies of the archive to cloud storage (never microdata); the site's daily visit counts into the archive |
| `schedule.py` | The daily trigger: systemd units on Linux, Task Scheduler on Windows |
| `backfill.py`, `migrate.py` | One-offs: adding hand-downloaded files; moving a setup from the project's earlier name |

## Rules the code keeps

- **Nothing is guessed.** A file in an unexpected format stops the run with `FormatError`.
- **Reproducible to the byte.** Queries whose rows feed an output are sorted (`ORDER BY`), text is
  written with `\n` line endings, Parquet through `module1.output.parquet_connection()`.
- **Standard library first.** Outside `local/`, no pandas or numpy: CI runs without them.
- **Microdata stay put.** Any step that publishes or copies archive files calls
  `archive.local_only.check()` first.
- **Polite fetching.** One request at a time, with a pause, and `robots.txt` respected.
