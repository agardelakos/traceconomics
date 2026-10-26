---
title: "Open data"
summary: "Every number on this site, for every topic and country, as files you can download, cite and rebuild."
sources: []
---
## How the files are laid out

Every topic publishes its files per country, in one folder each:

`/data/v1/{country}/{topic}/latest/`

The country is its two-letter code (`gr` for Greece); the topic is a short code (`m1` for inflation by group). `latest` always holds the current release. `v1` is the format version: a change that would break existing readers gets a new version, and the old one stays.

Each folder holds the topic's tables (Parquet, and CSV where listed), a `metadata.json` that describes the tables, their options and their sources, and a `SHA256SUMS` file to check the downloads. The bibliography behind every page is at `/data/v1/references.json`.

The files can be read straight from the web, with no account and no key: for example with DuckDB, which reads Parquet files over the web.

## Licence

The data on this site are published under the Creative Commons Attribution 4.0 licence (CC BY 4.0): you may reuse them, also commercially, if you credit the source. The code is published under the Apache 2.0 licence. Each dataset's page names the official sources it is built from, and the attribution they ask for.
