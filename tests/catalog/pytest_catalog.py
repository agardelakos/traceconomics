"""A pytest plugin that writes what was collected, for the catalog: never loaded in a normal run.

    python -m pytest --collect-only -q -p pytest_catalog --catalog-out items.json [paths…]

(with `tests/catalog` on PYTHONPATH; `collect.py` does this). One JSON object per collected test:
its node ID, the file and line, the function's docstring, the parameter-set ID of a parametrized
test, and the reasons of its skip and xfail marks (where defect links live). Nothing is run.
"""

import inspect
import json
from pathlib import Path


def pytest_addoption(parser):
    parser.addoption("--catalog-out", default=None, help="write the collected tests as JSON here")


def _reasons(item) -> list[str]:
    out = []
    for mark in item.iter_markers():
        if mark.name in ("skip", "skipif", "xfail"):
            reason = mark.kwargs.get("reason")
            if reason is None and mark.name == "skip" and mark.args:
                reason = mark.args[0]
            if reason:
                out.append(f"{mark.name}: {reason}")
    return out


def pytest_collection_finish(session):
    out = session.config.getoption("--catalog-out")
    if not out:
        return
    root = Path(session.config.rootpath)
    items = []
    for item in session.items:
        fn = getattr(item, "function", None)
        path, line, _ = item.location
        callspec = getattr(item, "callspec", None)
        items.append({
            "nodeid": item.nodeid,
            "base": item.nodeid.split("[", 1)[0],
            "file": Path(path).as_posix(),
            "line": (line or 0) + 1,
            "doc": inspect.getdoc(fn) if fn is not None else None,
            "param": callspec.id if callspec is not None else None,
            "reasons": _reasons(item),
            "markers": sorted({m.name for m in item.iter_markers()}),
        })
    Path(out).write_text(json.dumps({"root": root.as_posix(), "items": items}, indent=1),
                         encoding="utf-8", newline="\n")
