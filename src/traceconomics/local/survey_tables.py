"""Our survey tables: their names, where their inputs are found, and the code that shapes them.

`weights run` builds six tables per household budget survey year and `silc run` one per EU-SILC
year, from microdata that never leave the owner's machines. Each table's provenance line records
what it was built from: the code's fingerprint and every input file's hash. A build that reads the
tables must know they still match (`traceconomics check inputs`), so this module holds what that
check needs, with the standard library only: CI and the release build's check run without pandas.

Fingerprints. Each covers every file whose change can change the table: the code, and the data
files that code reads. `tests/test_survey_tables.py` walks the imports of `weights.py` and
`silc.py` and fails if a file they reach is neither covered here nor exempted there with its
reason, so the lists can't fall behind the code.
"""

from __future__ import annotations

import hashlib
import re
from importlib import resources
from pathlib import Path

from traceconomics.archive.store import Archive
from traceconomics.mapping_tables import OLD_TO_V1, V1_TO_2018

SOURCE = "oet-local"

# The household budget survey's tables, one of each per year, all from one `weights run`.
WEIGHTS = "hbs-weights-gr-{year}"
GROUPS = "hbs-groups-gr-{year}"
LIMITS = "hbs-limits-gr-{year}"
TYPES = "hbs-hhtypes-gr-{year}"
RENT = "hbs-rent-gr-{year}"
SPENDING_CHECK = "hbs-spending-gr-{year}"
HBS_TABLES = (WEIGHTS, GROUPS, LIMITS, TYPES, RENT, SPENDING_CHECK)
HBS_TABLE = re.compile(r"^hbs-(?:weights|groups|limits|hhtypes|rent|spending)-gr-(\d{4})$")

# EU-SILC: one table per survey year, from `silc run`.
SILC = "silc-tenure-gr-{year}"
SILC_TABLE = re.compile(r"^silc-tenure-gr-(\d{4})$")

# The microdata, as archived from ELSTAT (local only: never published or synced).
PUF_SOURCE = "elstat"
HBS_PUF = re.compile(r"^puf-hbs-(\d{4})$")
SILC_PUF = re.compile(r"^puf-.*silc-(\d{4})$")

# ELSTAT's published table 1.03 (household spending), English, one per survey year.
TABLE_103 = re.compile(r"SFA05_TB_AN_00_(\d{4})_103_F_EN\.xlsx?$")

# (package, file) of the code that shapes the household budget survey's tables.
WEIGHTS_CODE = (
    ("traceconomics.local", "puf.py"),
    ("traceconomics.local", "groups.py"),
    ("traceconomics.local", "shares.py"),
    ("traceconomics.local", "bootstrap.py"),
    ("traceconomics.local", "calibration.py"),
    ("traceconomics.local", "mapping.py"),
    ("traceconomics.local", "weights.py"),
    ("traceconomics.local", "v2.py"),
    ("traceconomics.local", "csv_table.py"),
    ("traceconomics.local", "survey_tables.py"),
    # Which survey years can rank households by income, and so get income groups.
    ("traceconomics.module1", "schedule.py"),
    # The household types the tables are built for (HOUSEHOLD_TYPES).
    ("traceconomics.module1", "index.py"),
    ("traceconomics.sources.elstat", "hbs_tables.py"),
    # Reads the EU-SILC tables the weights are calibrated to.
    ("traceconomics.sources", "oet_local.py"),
    ("traceconomics", "mapping_tables.py"),
)
WEIGHTS_DATA = (V1_TO_2018, OLD_TO_V1, "hbs_puf_missing_items.toml", "hbs_published_cvs.toml", "hbs_puf_releases.toml")

SILC_CODE = (
    ("traceconomics.local", "silc.py"),
    ("traceconomics.local", "csv_table.py"),
    ("traceconomics.local", "survey_tables.py"),
)
SILC_DATA: tuple[str, ...] = ()

SHORT = 16  # characters of a fingerprint written into a table's provenance


def _digest(code, data) -> str:
    # Line endings are normalised: a Windows checkout (CRLF) and a Linux one (LF) of the same code
    # must give the same fingerprint.
    h = hashlib.sha256()
    for package, name in code:
        h.update(resources.files(package).joinpath(name).read_bytes().replace(b"\r\n", b"\n"))
    for name in data:
        h.update(resources.files("traceconomics.data").joinpath(name).read_bytes().replace(b"\r\n", b"\n"))
    return h.hexdigest()


def weights_fingerprint() -> str:
    """sha256 over the code and data files that shape the household budget survey's tables."""
    return _digest(WEIGHTS_CODE, WEIGHTS_DATA)


def silc_fingerprint() -> str:
    """sha256 over the code that shapes the EU-SILC tables."""
    return _digest(SILC_CODE, SILC_DATA)


def mapping_hashes() -> dict[str, str]:
    """The mapping tables' hashes as the provenance records them (raw bytes, 12 characters)."""
    return {
        name: hashlib.sha256(resources.files("traceconomics.data").joinpath(name).read_bytes()).hexdigest()[:12]
        for name in (V1_TO_2018, OLD_TO_V1)
    }


def archived_tables(archive: Archive) -> dict[int, Path]:
    """The newest archived English table 1.03 per survey year."""
    found: dict[int, tuple[str, Path]] = {}
    for source, dataset in archive.datasets():
        if source != "elstat" or not dataset.startswith("doc-"):
            continue
        rec = archive.latest(source, dataset)
        m = TABLE_103.search(archive.manifest(rec).get("original_name") or "")
        if m and (int(m.group(1)) not in found or rec["retrieved_at"] > found[int(m.group(1))][0]):
            found[int(m.group(1))] = (rec["retrieved_at"], archive.root / rec["path"])
    return {y: p for y, (_, p) in sorted(found.items())}
