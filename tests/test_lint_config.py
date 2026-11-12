"""The formatters and linters never reach files that must stay as they are.

Saved publisher files (tests/fixtures/) are kept byte for byte so each can be checked against the
original; the reference data tables, the site's served files and generated output are not source
code; the Code of Conduct is kept as published. Each tool's configuration keeps them out. These tests
read those configurations, so an exclusion removed by mistake fails here before any tool rewrites a
protected file. They read files only: no formatter or linter runs.
"""

import json
import re
import tomllib
from pathlib import Path

import pytest

pytestmark = pytest.mark.repository

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"


def ruff() -> dict:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["ruff"]


def prettier_ignored() -> set[str]:
    lines = (SITE / ".prettierignore").read_text(encoding="utf-8").splitlines()
    return {line.strip() for line in lines if line.strip() and not line.startswith("#")}


def scripts() -> dict[str, str]:
    return json.loads((SITE / "package.json").read_text(encoding="utf-8"))["scripts"]


def test_ruff_reaches_only_the_projects_python():
    """PY-STYLE-001: Ruff formats and lints only the project's own Python, never the fixtures

    Given Ruff's settings in pyproject.toml
    When its file scope is read
    Then it includes only the package, the tests and the CI scripts
    And it excludes tests/fixtures/
    And the exclusion holds even for a path given on the command line (force-exclude)
    """
    cfg = ruff()
    assert cfg["include"] == ["src/**/*.py", "tests/**/*.py", ".github/scripts/**/*.py"]
    assert "tests/fixtures" in cfg["extend-exclude"]
    assert cfg["force-exclude"] is True


def test_prettier_ignores_every_protected_path():
    """PY-STYLE-002: Prettier's ignore file lists every path that must not be rewritten

    Given the site's .prettierignore
    When its entries are read
    Then it lists the fixtures, the Code of Conduct, the served files, the build output, the
      coverage reports and the files npm writes
    """
    required = {"../tests/fixtures/", "../CODE_OF_CONDUCT.md", "public/", "dist/", "coverage/",
                "package.json", "package-lock.json"}
    assert required <= prettier_ignored(), sorted(required - prettier_ignored())


def test_prettier_scripts_check_what_they_write():
    """PY-STYLE-003: the format and format:check scripts cover the same files with the same settings

    Given the site's npm scripts
    When format and format:check are compared
    Then they differ only in --write against --check
    And both name the config file and the ignore file explicitly (files outside site/ would
      otherwise find neither)
    And none of their file patterns reaches the reference data tables
    """
    fmt, check = scripts()["format"], scripts()["format:check"]
    assert fmt.replace("--write", "--check") == check
    assert "--config .prettierrc.json" in check and "--ignore-path .prettierignore" in check
    patterns = re.findall(r'"([^"]+)"', check)
    assert patterns, check
    # Under ../src/ only the package README is formatted; nothing reaches the data tables.
    outside = [p for p in patterns if "traceconomics/data" in p or (p.startswith("../src/") and not p.endswith("README.md"))]
    assert not outside, outside


def test_eslint_ignores_served_and_generated_files():
    """PY-STYLE-004: ESLint skips the served files and generated output

    Given the site's eslint.config.mjs
    When its ignores are read
    Then they include public/, dist/ and coverage/
    """
    text = (SITE / "eslint.config.mjs").read_text(encoding="utf-8")
    found = re.search(r"ignores:\s*\[([^\]]*)\]", text)
    assert found, "no ignores list in eslint.config.mjs"
    ignores = set(re.findall(r'"([^"]+)"', found.group(1)))
    assert {"public/", "dist/", "coverage/"} <= ignores, ignores
