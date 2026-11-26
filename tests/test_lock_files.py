"""The hashed lock files agree with pyproject.toml's pins.

CI and the server install from the lock files only (`pip install --require-hashes`), so a pin
changed in pyproject.toml without regenerating them would be silently ignored. The command that
regenerates each one is in its header."""

import re
import tomllib
from pathlib import Path

import pytest

pytestmark = pytest.mark.repository

ROOT = Path(__file__).parent.parent
PIN = re.compile(r"^([A-Za-z0-9._-]+)==(\S+)")
HASH = re.compile(r"--hash=sha256:[0-9a-f]{64}")


def norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def pins(requirements: list[str]) -> dict[str, str]:
    return {norm(m[1]): m[2] for r in requirements if (m := PIN.match(r))}


LOCKS = [
    ("requirements-dev.txt", ["dev"]),
    ("requirements-local.txt", ["local"]),
    ("requirements-selenium.txt", ["dev", "selenium"]),
    ("requirements-mutation.txt", ["dev", "mutation"]),
]


def problems(root: Path = ROOT) -> list[str]:
    """Where the lock files under root disagree with its pyproject.toml, one line each.

    The Selenium browser tests and mutation testing each have a lock of their own (with the dev
    extra), so their dependencies never enter the others.
    """
    with open(root / "pyproject.toml", "rb") as f:
        project = tomllib.load(f)["project"]
    base = pins(project["dependencies"])
    out = []
    for name, extras in LOCKS:
        text = (root / name).read_text(encoding="utf-8")
        joined = text.replace("\\\n", " ")
        lines = [line for line in joined.splitlines() if line and not line.lstrip().startswith("#")]
        out += [f"{name}: no hash for {line.split()[0]}" for line in lines if not HASH.search(line)]
        have = pins(lines)
        wanted = dict(base)
        for extra in extras:
            wanted |= pins(project["optional-dependencies"][extra])
        out += [
            f"{name}: {package} {have.get(package)}, pyproject {version}"
            for package, version in wanted.items()
            if have.get(package) != version
        ]
        # The build backend is locked too: the project is installed without build isolation.
        if "setuptools" not in have:
            out.append(f"{name}: setuptools missing")
        out += [f"{name}: not compiled for the {extra} extra" for extra in extras if f"--extra={extra}" not in text]
    return out


def test_lock_files_match_pyproject():
    """PY-LOCK-001: the hashed lock files match pyproject.toml's pins

    Given pyproject.toml's base dependencies and extras
    And the dev, local, selenium and mutation lock files
    When each lock file is read
    Then every requirement line in it carries a SHA-256 hash
    And every base pin and every pin of its extras is locked at the same version
    And setuptools is locked, since the project installs without build isolation
    And the file's header says it was compiled for each of its extras

    The Selenium browser tests and mutation testing each have a lock of their own (with the dev
    extra), so their dependencies never enter the others.
    """
    assert problems() == []
