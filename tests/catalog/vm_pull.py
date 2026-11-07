"""Release runs into run records: read what release builds uploaded to the test-results bucket.

    python -I tests/catalog/vm_pull.py --store DIR --out OUT_DIR      (link from TESTRESULTS_READ_URL)

Release builds run the browser tests on real data and upload each step's results through a
write-only link limited to `results/` (the builds hold no GitHub credential). Layout, one folder
per step run:

    results/<build>/<step>-<started>/meta.json        written last: the folder is complete
    results/<build>/<step>-<started>/playwright.json  the suite's own JSON report (not for "promote")

`meta.json`: {"schema": 1, "build", "commit", "step": "ui-test" | "smoke" | "promote",
"started": "YYYY-MM-DDTHH:MM:SSZ", "environment": {…}, "result": "passed" | "failed"}.

The read link lists and downloads only. Everything read is checked before use: the names, the
sizes, the JSON, every field of meta.json and the finished record (history.check_record). A folder
that fails is reported on the run's page and skipped, never half-stored; one already in DIR (the
branch `test-history`) is skipped quietly. Records are written to OUT_DIR for the push script.

Standard library only.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import history  # noqa: E402

FOLDER = re.compile(r"^results/([0-9]{8}T[0-9]{6}Z)/(ui-test|smoke|promote)-([0-9]{8}T[0-9]{6}Z)/(meta|playwright)\.json$")
MAX_BYTES = 20_000_000          # a Playwright report of the full suite is a few MB
ENV_KEYS = {"platform", "browser", "data", "runner"}


def fetch(url: str, limit: int = MAX_BYTES) -> bytes:
    with urllib.request.urlopen(url, timeout=60) as r:          # noqa: S310 (an https link we were given)
        body = r.read(limit + 1)
    if len(body) > limit:
        raise ValueError("too large")
    return body


def listing(base: str, get=fetch) -> list[dict]:
    """Every object under results/, following the listing's pages."""
    out, start = [], None
    while True:
        q = {"prefix": "results/", "fields": "name,size"}
        if start:
            q["start"] = start
        page = json.loads(get(f"{base}?{urllib.parse.urlencode(q)}", 5_000_000))
        out += page.get("objects", [])
        start = page.get("nextStartWith")
        if not start:
            return out


def check_meta(meta: dict, build: str, step: str) -> list[str]:
    problems = []
    if meta.get("schema") != 1:
        problems.append("unknown schema")
    if meta.get("build") != build or meta.get("step") != step:
        problems.append("build or step differs from its folder")
    if not re.fullmatch(r"[0-9a-f]{7,40}", str(meta.get("commit") or "")):
        problems.append("no commit")
    if meta.get("result") not in ("passed", "failed"):
        problems.append("no result")
    env = meta.get("environment")
    if not isinstance(env, dict) or not set(env) <= ENV_KEYS or not all(isinstance(v, str) and len(v) < 80 for v in env.values()):
        problems.append("bad environment")
    return problems


def pull(base: str, store: Path, out: Path, get=fetch) -> tuple[list[Path], list[str]]:
    catalog_path = store / "catalog.json"
    folders: dict[tuple[str, str, str], dict[str, int]] = {}
    for o in listing(base, get):
        m = FOLDER.match(o.get("name", ""))
        if m:
            folders.setdefault(m.groups()[:3], {})[m.group(4)] = int(o.get("size") or 0)
    written, problems = [], []
    out.mkdir(parents=True, exist_ok=True)
    if not catalog_path.is_file():                              # the very first run: no catalog yet
        catalog_path = out / "empty-catalog.json"
        history.write(catalog_path, {"cases": []})
    for (build, step, started), files in sorted(folders.items()):
        run_id = f"{build}-{step}-{started}"
        where = f"results/{build}/{step}-{started}/"
        if any((store / "runs" / step).glob(f"*_{run_id}.json")):
            continue                                            # stored already
        if "meta" not in files:
            continue                                            # still uploading, or abandoned
        pw_file = None
        try:
            meta = json.loads(get(base + where + "meta.json", 100_000))
            bad = check_meta(meta, build, step)
            if bad:
                raise ValueError(", ".join(bad))
            iso = f"{started[:4]}-{started[4:6]}-{started[6:8]}T{started[9:11]}:{started[11:13]}:{started[13:15]}Z"
            env = [f"{k}={v}" for k, v in sorted(meta["environment"].items())]
            if step != "promote":
                if "playwright" not in files:
                    raise ValueError("no playwright.json")
                pw_file = out / f"{run_id}.playwright.json"
                pw_file.write_bytes(get(base + where + "playwright.json"))
                json.loads(pw_file.read_text(encoding="utf-8"))      # valid JSON, or ValueError
            a = SimpleNamespace(catalog=catalog_path, junit=None, playwright=pw_file, vitest=None, env=env,
                                run_id=run_id, trigger=step, commit=meta["commit"], build=build, started=iso,
                                run_url=None)
            rec = history.record(a)
            if step == "promote":
                result = meta["result"]
                rec["suites"] = {"promote-check": {"passed": int(result == "passed"), "failed": int(result == "failed"),
                                                   "flaky": 0, "skipped": 0, "duration": 0.0}}
            bad = history.check_record(rec)
            if bad:
                raise ValueError(", ".join(bad))
            path = out / f"{run_id}.json"
            history.write(path, rec)
            written.append(path)
        except (ValueError, OSError, KeyError, TypeError) as e:
            problems.append(f"{where}: {e}")
        finally:
            if pw_file is not None and pw_file.exists():
                pw_file.unlink()                                # the record holds what's needed
    return written, problems


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--store", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    a = ap.parse_args(argv)
    base = os.environ.get("TESTRESULTS_READ_URL", "").strip()
    if not base:
        print("no read link (TESTRESULTS_READ_URL): release runs not pulled")
        return 0
    if not base.endswith("/o/"):
        print("the read link should end in /o/")
        return 1
    written, problems = pull(base, a.store, a.out)
    for p in problems:
        print(f"skipped {p}")
    print(f"{len(written)} new release runs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
