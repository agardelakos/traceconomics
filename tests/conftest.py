from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
SELENIUM = Path(__file__).parent / "selenium"


def pytest_addoption(parser):
    group = parser.getgroup("selenium", "Selenium browser tests (tests/selenium)")
    group.addoption("--selenium", action="store_true",
                    help="collect the Selenium browser tests; they need a built site (site/dist) and Selenium")
    group.addoption("--base-url", default=None,
                    help="run the Selenium tests against this server instead of serving site/dist")


def pytest_ignore_collect(collection_path, config):
    # The browser tests need a built site, Chrome and the `selenium` extra, none of which the plain
    # test run has: they are collected only when asked for.
    if not config.getoption("--selenium") and collection_path == SELENIUM:
        return True
    return None


@pytest.fixture
def fixture_bytes():
    return lambda name: (FIXTURES / name).read_bytes()
