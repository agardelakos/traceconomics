import ast
from pathlib import Path

import pytest
from guards import NetworkGuard

try:
    from coverage import Coverage
except ImportError:  # coverage is a dev pin; a run without it simply isn't measured
    Coverage = None

FIXTURES = Path(__file__).parent / "fixtures"
SELENIUM = Path(__file__).parent / "selenium"

# Every test belongs to one layer, so the coverage figure can say what each layer adds (see
# tests/coverage/overview.py). A test file names its layer once (module-level `pytestmark`); a test
# that differs from its file overrides it with its own mark, and the closest mark wins.
#   unit         one of our components on its own; it may use its own files (a temporary folder),
#                its collaborators are faked or absent
#   integration  two or more of our components meeting through a real resource: an archive on disk,
#                the observation store, the run job, module1's outputs read by the site export
#   repository   checks on the repository's own files (fixtures, lock files, wiki pages, the test
#                tooling): no package code runs
# The Selenium browser tests (tests/selenium) test the built site, not the package: no layer here.
LAYERS = ("unit", "integration", "repository")


def layer(item) -> str | None:
    """The test's layer: its closest layer mark (its own, else its file's)."""
    return next((m.name for m in item.iter_markers() if m.name in LAYERS), None)


def file_layer(path: Path) -> str | None:
    """The layer a test file declares in `pytestmark = pytest.mark.<layer>`, read without importing it."""
    for node in ast.parse(path.read_bytes()).body:
        if (
            isinstance(node, ast.Assign)
            and any(getattr(t, "id", None) == "pytestmark" for t in node.targets)
            and isinstance(node.value, ast.Attribute)
            and node.value.attr in LAYERS
        ):
            return node.value.attr
    return None


def _measured(path: Path) -> bool:
    return SELENIUM not in path.parents


def pytest_addoption(parser):
    group = parser.getgroup("selenium", "Selenium browser tests (tests/selenium)")
    group.addoption(
        "--selenium",
        action="store_true",
        help="collect the Selenium browser tests; they need a built site (site/dist) and Selenium",
    )
    group.addoption(
        "--base-url", default=None, help="run the Selenium tests against this server instead of serving site/dist"
    )


def pytest_ignore_collect(collection_path, config):
    # The browser tests need a built site, Chrome and the `selenium` extra, none of which the plain
    # test run has: they are collected only when asked for.
    if not config.getoption("--selenium") and collection_path == SELENIUM:
        return True
    return None


def pytest_collection_modifyitems(config, items):
    # A missing layer is a collection error, not a default: the choice is the test author's.
    measured = [item for item in items if _measured(item.path)]
    problems = sorted(
        {item.path.relative_to(config.rootpath).as_posix() for item in measured if file_layer(item.path) is None}
    )
    problems += [item.nodeid for item in measured if layer(item) is None]
    if problems:
        raise pytest.UsageError(
            "every test file needs `pytestmark = pytest.mark.<layer>`, one of "
            f"{', '.join(LAYERS)} (tests/conftest.py explains them):\n  " + "\n  ".join(problems)
        )


# Each line run is labelled `<layer>|<test>` (a dynamic context): the layer gives the badges' split
# (tests/coverage/overview.py reads the part before `|`), the test gives the code map
# (tests/coverage/code_map.py: which test cases run which code). While a test file is imported the
# test is `<file>::<import>`: the package lines that run then are module-level code (imports,
# definitions), and only the first file to import a module records them, so the map treats them as
# one set, "imported", never as the work of that file's tests.
IMPORT = "::<import>"


def _context(label: str):
    """Label the coverage being recorded, when coverage is running; else nothing."""
    cov = Coverage.current() if Coverage is not None else None
    if cov is not None:
        cov.switch_context(label)


@pytest.hookimpl(wrapper=True)
def pytest_make_collect_report(collector):
    # Importing a test file runs the package's module-level code (imports, definitions): those lines
    # count for the file's layer, read from its source since the module isn't imported yet.
    if not (isinstance(collector, pytest.Module) and _measured(collector.path)):
        return (yield)
    _context(f"{file_layer(collector.path) or ''}|{collector.nodeid}{IMPORT}")
    try:
        return (yield)
    finally:
        _context("")


@pytest.hookimpl(wrapper=True)
def pytest_runtest_protocol(item, nextitem):
    # Setup, call and teardown alike: a fixture's work counts for the test that asked for it.
    if not _measured(item.path):
        return (yield)
    _context(f"{layer(item) or ''}|{item.nodeid}")
    try:
        return (yield)
    finally:
        _context("")


@pytest.fixture(autouse=True)
def no_network(request, monkeypatch):
    # No test reaches the network (tests/guards.py). The Selenium tests are left out: they drive a
    # browser that Selenium Manager fetches once per machine, outside any test's code.
    if not _measured(request.node.path):
        yield None
        return
    guard = NetworkGuard(monkeypatch)
    yield guard
    if (problem := guard.problem()) is not None:
        pytest.fail(problem, pytrace=False)


@pytest.fixture
def fixture_bytes():
    return lambda name: (FIXTURES / name).read_bytes()
