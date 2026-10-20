"""Which archived datasets hold microdata and must stay on machines the owner controls.

The raw archive is meant to be published, so anyone can trace a number back to
its source file. Microdata are the exception: the files ELSTAT provides for
research may be used here, but only aggregates computed from them are shared. They may sit
on the owner's own machines (a computer, a home backup drive, a private server the owner runs),
never on a public site, in shared or cloud storage, or in a release.
The list is in `traceconomics/data/local_only.toml`; anything that publishes or copies
archive files must pass them through `check` first.
"""

from __future__ import annotations

import tomllib
from collections.abc import Iterable
from functools import cache
from importlib import resources


class LocalOnlyError(Exception):
    """An attempt to publish or copy microdata."""


@cache
def _rules() -> tuple[tuple[str, ...], frozenset[str]]:
    data = tomllib.loads(resources.files("traceconomics.data").joinpath("local_only.toml").read_text(encoding="utf-8"))
    return tuple(data["patterns"]), frozenset(data.get("exceptions", []))


def is_local_only(source: str, dataset: str) -> bool:
    name = f"{source}/{dataset}"
    patterns, exceptions = _rules()
    if name in exceptions:
        return False
    return any(name.startswith(p[:-1]) if p.endswith("*") else name == p for p in patterns)


def check(items: Iterable[tuple[str, str]]) -> None:
    """Raise if any (source, dataset) is local-only. Call before publishing or syncing."""
    bad = sorted(f"{s}/{d}" for s, d in items if is_local_only(s, d))
    if bad:
        raise LocalOnlyError(f"microdata must not leave this machine: {', '.join(bad[:5])}"
                             + (f" and {len(bad) - 5} more" if len(bad) > 5 else ""))
