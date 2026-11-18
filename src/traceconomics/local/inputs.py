"""Do our survey tables still match what they were built from? (`traceconomics check inputs`)

The tables `weights run` and `silc run` archive (`survey_tables`) are a third kind of input,
neither code nor a publisher's file: they stay as they were built until someone runs those
commands again. Each table's provenance line names the code's fingerprint and every input's
hash, so a table is stale when any of these moved since:

- the code that shapes it (a deploy);
- the survey file it read (ELSTAT re-issues a public use file);
- ELSTAT's table 1.03 it was checked against;
- the mapping tables;
- the EU-SILC tables its weights are calibrated to (a `silc run` alone makes every household
  budget survey table stale);
- the other tables of its year (the six are written one after another, so a build that reads
  them during a `weights run` sees two runs at once).

Standard library only: the release build runs this before any step reads the tables, and CI
runs its tests without pandas. A stale table fails the check; nothing here rebuilds anything.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

from traceconomics.archive.store import Archive
from traceconomics.local import survey_tables as st

PROVENANCE = "# provenance: "
SILC_FIX = "rebuild the EU-SILC tables, then the household budget survey's: `silc run`, then `weights run`"
HBS_FIX = "rebuild the household budget survey's tables: `weights run`"


@dataclass
class Report:
    problems: list[str] = field(default_factory=list)  # SILC's first: the weights depend on them
    checked: list[str] = field(default_factory=list)  # one line per table set that matches
    silc_stale: bool = False

    @property
    def ok(self) -> bool:
        return not self.problems

    @property
    def fix(self) -> str | None:
        if self.ok:
            return None
        return SILC_FIX if self.silc_stale else HBS_FIX


def provenance(path: Path) -> str | None:
    """The table's provenance line (the JSON after `# provenance: `), as written."""
    with path.open(encoding="utf-8") as f:
        for line in f:
            if not line.startswith("#"):
                return None
            if line.startswith(PROVENANCE):
                return line[len(PROVENANCE) :].rstrip("\n")
    return None


def _years(archive: Archive, source: str, pattern) -> dict[int, str]:
    out = {}
    for src, dataset in archive.datasets():
        if src == source and (m := pattern.match(dataset)):
            out[int(m.group(1))] = dataset
    return out


def _newest(archive: Archive, source: str, dataset: str) -> str | None:
    """`source/dataset@hash` of the newest archived file, as provenance lines name inputs."""
    rec = archive.latest(source, dataset)
    return f"{source}/{dataset}@{rec['sha256'][:12]}" if rec else None


def _named_input(archive: Archive, named: str) -> str | None:
    """None if `source/dataset@hash` is still the newest file of its dataset, else what's wrong."""
    try:
        where, _ = named.rsplit("@", 1)
        source, dataset = where.split("/", 1)
    except ValueError:
        return f"an input it names can't be read: {named!r}"
    now = _newest(archive, source, dataset)
    if now is None:
        return f"its input {where} is not in this archive"
    if now != named:
        return f"built from {named}, the archive's newest is {now.rsplit('@', 1)[1]}"
    return None


def check(archive: Archive) -> Report:
    report = Report()
    _check_silc(archive, report)
    _check_hbs(archive, report)
    return report


def _check_silc(archive: Archive, report: Report) -> None:
    code = st.silc_fingerprint()[: st.SHORT]
    surveys = _years(archive, st.PUF_SOURCE, st.SILC_PUF)
    tables = _years(archive, st.SOURCE, st.SILC_TABLE)
    for year in sorted(surveys.keys() | tables.keys()):
        name = st.SILC.format(year=year)
        found = _silc_problems(archive, year, name, surveys.get(year), code)
        if found:
            report.silc_stale = True
            report.problems += [f"EU-SILC {year} ({name}): {p}" for p in found]
        else:
            report.checked.append(f"EU-SILC {year}: matches")


def _silc_problems(archive: Archive, year: int, name: str, survey: str | None, code: str) -> list[str]:
    rec = archive.latest(st.SOURCE, name)
    if rec is None:
        return ["no table, though the survey file is archived"]
    line = provenance(archive.root / rec["path"])
    if line is None:
        return ["no provenance line"]
    prov = json.loads(line)
    found = []
    if prov.get("code_fingerprint") != code:
        found.append(f"built by other code (fingerprint {prov.get('code_fingerprint')}, the code's is {code})")
    if survey is None:
        found.append("its survey file is not in this archive, so the table can't be checked")
    elif prov.get("survey") != _newest(archive, st.PUF_SOURCE, survey):
        found.append(
            f"built from {prov.get('survey')}, the archive's newest is {_newest(archive, st.PUF_SOURCE, survey)}"
        )
    return found


def _check_hbs(archive: Archive, report: Report) -> None:
    code = st.weights_fingerprint()[: st.SHORT]
    mapping = st.mapping_hashes()
    surveys = _years(archive, st.PUF_SOURCE, st.HBS_PUF)
    years = set(surveys)
    for _, dataset in archive.datasets():
        if m := st.HBS_TABLE.match(dataset):
            years.add(int(m.group(1)))
    table_103 = st.archived_tables(archive) if years else {}
    for year in sorted(years):
        found = _hbs_problems(archive, year, surveys.get(year), table_103.get(year), code, mapping)
        if found:
            report.problems += [f"household budget survey {year}: {p}" for p in found]
        else:
            report.checked.append(f"household budget survey {year}: all {len(st.HBS_TABLES)} tables match")


def _hbs_problems(
    archive: Archive, year: int, survey: str | None, table_103: Path | None, code: str, mapping: dict
) -> list[str]:
    lines = {}
    for name in st.HBS_TABLES:
        rec = archive.latest(st.SOURCE, name.format(year=year))
        lines[name] = provenance(archive.root / rec["path"]) if rec else None
    missing = [n.format(year=year) for n, line in lines.items() if line is None]
    if missing:
        return ["no table or no provenance line: " + ", ".join(missing)]
    if len(set(lines.values())) > 1:
        return [f"its {len(st.HBS_TABLES)} tables come from different runs (read during a `weights run`?)"]
    prov = json.loads(next(iter(lines.values())))
    found = []
    if prov.get("code_fingerprint") != code:
        found.append(f"built by other code (fingerprint {prov.get('code_fingerprint')}, the code's is {code})")
    if survey is None:
        found.append("its survey file is not in this archive, so the tables can't be checked")
    elif prov.get("survey") != _newest(archive, st.PUF_SOURCE, survey):
        found.append(
            f"built from {prov.get('survey')}, the archive's newest is {_newest(archive, st.PUF_SOURCE, survey)}"
        )
    if table_103 is None:
        found.append("no table 1.03 for the year in this archive")
    elif prov.get("table_103") != hashlib.sha256(table_103.read_bytes()).hexdigest()[:12]:
        found.append("checked against an older table 1.03 than the archive's newest")
    if prov.get("mapping") != mapping:
        found.append("built with other mapping tables")
    silc = (prov.get("tenure_target") or {}).get("silc")
    if not silc:
        found.append("built before the weights were calibrated to EU-SILC's tenure split")
    else:
        found += [p for named in silc if (p := _named_input(archive, named))]
    return found
