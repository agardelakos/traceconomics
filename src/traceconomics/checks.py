"""Format checks shared by the parsers.

A source file that doesn't look as expected stops the pipeline with a clear
message. Parsers never guess: a changed layout is a reason to look, not to
carry on with numbers that may be wrong.
"""

from __future__ import annotations


class FormatError(Exception):
    """A source file isn't in the expected format."""


def require(ok: bool, message: str) -> None:
    if not ok:
        raise FormatError(message)


def examples(items, n: int = 5) -> str:
    """A short, readable list of offending values for an error message."""
    items = list(items)
    shown = ", ".join(repr(x) for x in items[:n])
    return shown + (f" (and {len(items) - n} more)" if len(items) > n else "")
