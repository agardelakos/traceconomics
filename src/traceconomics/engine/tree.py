"""The COICOP tree, read from the codes themselves.

Codes are plain digits: a division has 2 (`01` food), a group 3 (`011`), a
class 4 (`0111`), a subclass 5 (`01111`), and some countries go one level
further (6). A code's parent is the code with its last digit removed; the
parent of a division is all items, `TOTAL`. Codes that aren't digits (special
aggregates such as energy) are not part of the tree.
"""

from __future__ import annotations

TOTAL = "TOTAL"


def is_item(code: str) -> bool:
    return code.isdigit() and len(code) >= 2


def ancestors(code: str) -> list[str]:
    """Parents up to the division, nearest first. `TOTAL` is never included: pricing an
    item with the all-items index would make an aggregate partly depend on itself."""
    return [code[:n] for n in range(len(code) - 1, 1, -1)]


def leaves(weights: dict[str, float]) -> dict[str, float]:
    """The items an aggregate is built from: codes with a positive weight and no
    weighted code below them.

    A parent whose children carry only part of its weight is not a leaf; the
    part not covered by any child is left out and the remaining weights are
    rescaled. (Pricing that remainder with the parent's index was tested on
    Greek data and matched the official index less well, because the parent's
    published weight is rounded.)
    """
    items = {c: w for c, w in weights.items() if is_item(c)}
    bad = {c: w for c, w in items.items() if w < 0}
    if bad:
        raise ValueError(f"negative weights: {bad}")
    weighted = {c for c, w in items.items() if w > 0}
    has_weighted_child = {a for c in weighted for a in ancestors(c)}
    return {c: items[c] for c in weighted if c not in has_weighted_child}


def at_level(weights: dict[str, float], digits: int) -> dict[str, float]:
    """Only the codes with exactly this many digits, e.g. 2 for divisions."""
    return {c: w for c, w in weights.items() if is_item(c) and len(c) == digits}
