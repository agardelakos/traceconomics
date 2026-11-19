"""The survey tables' fingerprints cover every file that can change the tables.

A fingerprint is a list of files. A file it leaves out fails silently: a change there changes the
tables, the fingerprint stays the same, and `check inputs` passes stale tables. So these tests
walk the imports of the code that builds the tables and require every file they reach to be
either covered or exempted here with its reason.
"""

import ast
from importlib import resources
from pathlib import Path

import pytest

import traceconomics
from traceconomics.local import survey_tables as st

pytestmark = pytest.mark.unit

PACKAGE = Path(traceconomics.__file__).parent
DATA = PACKAGE / "data"

# Reached by the imports, but can't change a table's numbers. Each reason must stay true: if one of
# these files starts to shape the tables, move it into the fingerprint's list.
EXEMPT_WEIGHTS = {
    "traceconomics": "the version string; written into the provenance, not into any number",
    "traceconomics.archive": "an empty package",
    "traceconomics.archive.store": "reads and writes archived files; no figures",
    "traceconomics.checks": "raises errors on bad input; no figures",
    "traceconomics.local": "an empty package",
    "traceconomics.module1": "an empty package",
    "traceconomics.module1.prices": "reached through module1.index's own imports; the tables use only "
    "index.py's HOUSEHOLD_TYPES (covered)",
    "traceconomics.module1.weights_used": "as module1.prices",
    "traceconomics.module1.originals": "as module1.prices",
    "traceconomics.engine": "as module1.prices",
    "traceconomics.engine.chain": "as module1.prices",
    "traceconomics.engine.rates": "as module1.prices",
    "traceconomics.engine.tree": "as module1.prices",
    "traceconomics.sources": "an empty package",
    "traceconomics.sources.elstat": "ELSTAT's fetching code, run as the package above hbs_tables",
    "traceconomics.sources.base": "the HTTP client, reached through sources.elstat",
    "traceconomics.htmltext": "web page text, reached through sources.elstat",
    "traceconomics.sources.elstat.original07": "reached through module1.originals",
    "traceconomics.sources.elstat.calendar_pdf": "ELSTAT's release calendar PDF, reached through sources.elstat; "
    "release dates, no figures",
    "traceconomics.store": "an empty package",
    "traceconomics.store.query": "reached only by `mapping build`, which writes the mapping tables (covered as data)",
}
EXEMPT_SILC = {
    "traceconomics": EXEMPT_WEIGHTS["traceconomics"],
    "traceconomics.archive": EXEMPT_WEIGHTS["traceconomics.archive"],
    "traceconomics.archive.store": EXEMPT_WEIGHTS["traceconomics.archive.store"],
    "traceconomics.checks": EXEMPT_WEIGHTS["traceconomics.checks"],
    "traceconomics.local": EXEMPT_WEIGHTS["traceconomics.local"],
    "traceconomics.mapping_tables": "survey_tables reads two file names from it; the EU-SILC tables use no mapping",
}


def module_file(module: str) -> Path | None:
    p = PACKAGE.parent.joinpath(*module.split("."))
    if (p / "__init__.py").is_file():
        return p / "__init__.py"
    return p.with_suffix(".py") if p.with_suffix(".py").is_file() else None


def imported(path: Path) -> set[str]:
    """Our modules a file imports, at the top or inside a function (both run when the tables are
    built), with every package above them (Python runs each package's __init__)."""
    names = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("traceconomics"):
            names.add(node.module)
            names |= {f"{node.module}.{a.name}" for a in node.names if module_file(f"{node.module}.{a.name}")}
        elif isinstance(node, ast.Import):
            names |= {a.name for a in node.names if a.name.startswith("traceconomics")}
    return {".".join(n.split(".")[:i]) for n in names for i in range(1, n.count(".") + 2)}


def reached(start: str) -> set[str]:
    seen, todo = set(), [start]
    while todo:
        m = todo.pop()
        if m in seen or not (f := module_file(m)):
            continue
        seen.add(m)
        todo += imported(f)
    return seen


def _assigns(node, names: set[str]) -> bool:
    targets = node.targets if isinstance(node, ast.Assign) else [node.target] if isinstance(node, ast.AnnAssign) else []
    return any(isinstance(t, ast.Name) and t.id in names for t in targets)


def covered(code) -> set[str]:
    return {f"{package}.{name.removesuffix('.py')}" for package, name in code}


@pytest.mark.parametrize(
    ("start", "code", "exempt"),
    [
        ("traceconomics.local.weights", st.WEIGHTS_CODE, EXEMPT_WEIGHTS),
        ("traceconomics.local.silc", st.SILC_CODE, EXEMPT_SILC),
    ],
    ids=["weights", "silc"],
)
def test_every_file_the_table_code_reaches_is_fingerprinted_or_exempted(start, code, exempt):
    """PY-TABLES-001: every module the table-building code imports is in its fingerprint or exempted with a reason

    Given the module that builds a kind of survey table (weights.py, silc.py)
    When its imports are followed through our package, including those inside functions
    Then every module reached is in that table's fingerprint list or in its exemptions
    And every listed or exempted module is one the imports reach, so neither list holds dead entries
    And no module is both listed and exempted
    """
    found = reached(start)
    listed = covered(code)
    assert found - listed - exempt.keys() == set(), "fingerprint these, or exempt them with a reason"
    assert (listed | exempt.keys()) - found == set(), "no longer reached: remove from the list"
    assert listed & exempt.keys() == set()


@pytest.mark.parametrize(
    ("code", "data"), [(st.WEIGHTS_CODE, st.WEIGHTS_DATA), (st.SILC_CODE, st.SILC_DATA)], ids=["weights", "silc"]
)
def test_every_data_file_the_covered_code_names_is_fingerprinted(code, data):
    """PY-TABLES-002: every data file named in the fingerprinted code is in the fingerprint

    Given the files in the package's data folder
    And the code a fingerprint covers
    When the code's string constants are searched for those file names
    Then every data file named there is in the fingerprint's data list
    """
    files = {p.name for p in DATA.iterdir() if p.is_file()}
    named = set()
    for package, name in code:
        tree = ast.parse(resources.files(package).joinpath(name).read_text(encoding="utf-8"))
        # survey_tables.py names every fingerprint's data files in these lists without reading them.
        tree.body = [n for n in tree.body if not _assigns(n, {"WEIGHTS_DATA", "SILC_DATA"})]
        named |= {n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and n.value in files}
    assert named - set(data) == set()


def test_the_fingerprints_ignore_line_endings(tmp_path, monkeypatch):
    """PY-TABLES-003: a file checked out with Windows line endings gives the same fingerprint

    Given a code file and a data file with Unix line endings
    And the same two files with Windows line endings
    When each set is fingerprinted
    Then both give the same hash
    """

    def fingerprint(folder, newline):
        (folder / "code.py").write_bytes(f"a = 1{newline}b = 2{newline}".encode())
        (folder / "table.csv").write_bytes(f"x,y{newline}1,2{newline}".encode())
        monkeypatch.setattr(st.resources, "files", lambda package: folder)
        return st._digest([("any", "code.py")], ["table.csv"])

    (tmp_path / "lf").mkdir()
    (tmp_path / "crlf").mkdir()
    assert fingerprint(tmp_path / "lf", "\n") == fingerprint(tmp_path / "crlf", "\r\n")
