"""The package's reference data: which source datasets are parsed, and how codes are translated.

Kept as TOML files in `traceconomics/data/` so they can be read and reviewed without
reading code. Loaded once and cached.
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from functools import cache
from importlib import resources


class CatalogError(Exception):
    """The reference data is inconsistent, or names an unknown dataset."""

    pass


@dataclass(frozen=True)
class DatasetSpec:
    """One parsed store dataset as `datasets.toml` describes it: its archive sources, format and dimensions."""

    id: str  # e.g. "eurostat:prc_hicp_minr"
    source: str
    name: str
    archive: tuple[str, ...]
    format: str
    dimensions: tuple[str, ...]
    freq: str | None = None  # when all periods share one frequency
    coicop: str | None = None
    classification: str | None = None
    backcast_before: str | None = None
    release: str | None = None
    file_name: re.Pattern | None = None
    label_files: re.Pattern | None = None
    regions: bool = False  # the geo column also holds NUTS regions (the censuses)

    def covers(self, source: str, dataset: str) -> bool:
        """Whether an archived dataset is one this store dataset is built from (its `archive` list)."""
        for pattern in self.archive:
            src, _, name = pattern.partition("/")
            if src == source and (name.endswith("*") and dataset.startswith(name[:-1]) or name == dataset):
                return True
        return False

    def feeds(self, source: str, dataset: str, original_name: str | None) -> bool:
        """Whether an archived dataset (and file) feeds this store dataset."""
        if not self.covers(source, dataset):
            return False
        return self.file_name is None or bool(original_name and self.file_name.search(original_name))


def _load(name: str) -> dict:
    return tomllib.loads(resources.files("traceconomics.data").joinpath(name).read_text(encoding="utf-8"))


@cache
def datasets() -> dict[str, DatasetSpec]:
    """Every store dataset in `datasets.toml`, by id (`source:name`).

    Raises `CatalogError` when a dataset's COICOP or release dimension isn't one of its dimensions.
    """
    out = {}
    for source, entries in _load("datasets.toml").items():
        for name, e in entries.items():
            spec = DatasetSpec(
                id=f"{source}:{name}",
                source=source,
                name=name,
                archive=tuple(e["archive"]),
                format=e["format"],
                freq=e.get("freq"),
                dimensions=tuple(e["dimensions"]),
                coicop=e.get("coicop"),
                regions=bool(e.get("regions", False)),
                classification=e.get("classification"),
                backcast_before=e.get("backcast_before"),
                release=e.get("release"),
                file_name=re.compile(e["file_name"]) if "file_name" in e else None,
                label_files=re.compile(e["label_files"]) if "label_files" in e else None,
            )
            if spec.coicop and spec.coicop not in spec.dimensions:
                raise CatalogError(f"{spec.id}: coicop dimension {spec.coicop!r} isn't a dimension")
            if spec.release and spec.release not in spec.dimensions:
                raise CatalogError(f"{spec.id}: release dimension {spec.release!r} isn't a dimension")
            out[spec.id] = spec
    return out


def dataset(dataset_id: str) -> DatasetSpec:
    """The store dataset with this id; raises `CatalogError` if there is none."""
    try:
        return datasets()[dataset_id]
    except KeyError:
        raise CatalogError(f"unknown dataset {dataset_id!r}") from None


@dataclass(frozen=True)
class GeoMap:
    """How one source's geography codes are translated: renamed codes, codes kept as they are, aggregates."""

    rename: dict[str, str]
    keep: frozenset[str]
    aggregate_patterns: tuple[re.Pattern, ...]

    def is_aggregate(self, code: str) -> bool:
        """Whether the code is a group of countries (it matches an aggregate pattern)."""
        return any(p.match(code) for p in self.aggregate_patterns)

    def is_known(self, code: str) -> bool:
        """A source code we can place: renamed, kept, an aggregate, or already two capital letters."""
        return (
            code in self.rename
            or code in self.keep
            or self.is_aggregate(code)
            or re.fullmatch(r"[A-Z]{2}", code) is not None
        )


@cache
def geo(source: str) -> GeoMap:
    """The geography code map for one source, from `geo.toml`."""
    data = _load("geo.toml")
    src = data.get(source, {})
    return GeoMap(
        rename=dict(src.get("rename", {})),
        keep=frozenset(src.get("keep", {})),
        aggregate_patterns=tuple(re.compile(p) for p in data.get("aggregates", {}).get("patterns", [])),
    )
