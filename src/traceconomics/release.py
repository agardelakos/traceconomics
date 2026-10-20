"""Building a release: everything after the archive job, up to a private preview of the site.

`build` runs the steps below in order and stops at the first failure: update the store, compute
every series and the error bands, run the checks, write the site's data, build and test the
site, and upload it as a preview. Each build gets a folder (`<releases>/<id>/`) with every step's
log, the outputs, the built site, checksums of both and a report, which is emailed with the
preview link and what changed since the last release.

Nothing reaches the site's public address until the owner looks at the preview and promotes the
build (`promote`): a person checks every release before it is published.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from traceconomics import catalog
from traceconomics.archive.store import Archive, iso, sha256_file, stamp, utc_now
from traceconomics.config import CONFIG_ENV, Config
from traceconomics.job import RunLock
from traceconomics.notify import notify

PROMOTED = "promoted.json"
PREVIEW_URL = re.compile(r"https://[\w.-]+\.pages\.dev\S*")
LOG_TAIL = 40


@dataclass(frozen=True)
class Step:
    name: str
    argv: tuple[str, ...]
    cwd: Path | None = None


# A runner executes one step, writing its output to the log file, and returns the exit code.
Runner = Callable[[Step, dict, Path], int]


def run_step(step: Step, env: dict, log: Path) -> int:
    exe = shutil.which(step.argv[0]) or step.argv[0]    # npm and npx are .cmd files on Windows
    with log.open("w", encoding="utf-8") as f:
        f.write(f"$ {' '.join(step.argv)}\n")
        f.flush()
        return subprocess.run([exe, *step.argv[1:]], cwd=step.cwd, env=env, stdout=f,
                              stderr=subprocess.STDOUT).returncode


def _py(*args: str) -> tuple[str, ...]:
    return (sys.executable, "-I", "-m", "traceconomics", *args)


def steps(cfg: Config, folder: Path, build_id: str) -> list[Step]:
    r = cfg.release
    site, outputs = r.site_dir, folder / "outputs"
    return [
        Step("store", _py("store", "update")),
        Step("series", _py("module1", "run", "--out", str(outputs), "--combinations", "all")),
        Step("bands", _py("bands", "run", "--combinations", "all", "--replicates", str(r.replicates))),
        Step("store-bands", _py("store", "update")),
        Step("check-v1", _py("check", "v1")),
        Step("check-v1-cpi", _py("check", "v1-cpi")),
        Step("check-combos", _py("check", "combos", "--outputs", str(outputs))),
        Step("export", _py("export", "site", "--out", str(site / "public" / "data"), "--outputs", str(outputs))),
        Step("npm-ci", ("npm", "ci", "--no-audit", "--no-fund"), site),
        Step("site-check", ("npm", "run", "check"), site),
        Step("upload", _wrangler(site / "dist", r.pages_project, f"build-{build_id.lower()}"), site),
    ]


def _wrangler(folder: Path, project: str, branch: str) -> tuple[str, ...]:
    return ("npx", "--no-install", "wrangler", "pages", "deploy", str(folder),
            "--project-name", project, "--branch", branch, "--commit-dirty=true")


def _env(config_path: Path | None) -> dict:
    env = dict(os.environ)
    if config_path is not None:
        env[CONFIG_ENV] = str(config_path)
    env.setdefault("WRANGLER_SEND_METRICS", "false")
    return env


def feeds_store(archive: Archive, results) -> list[str]:
    """Which newly stored files feed the observation store (so a release is worth building)."""
    specs = catalog.datasets().values()
    out = []
    for r in results:
        if r.status != "stored" or r.path is None:
            continue
        manifest = Path(r.path).parent / "manifest.json"
        name = None
        if manifest.is_file():
            name = json.loads(manifest.read_text(encoding="utf-8")).get("original_name")
        if any(s.feeds(r.source, r.dataset, name) for s in specs):
            out.append(f"{r.source}/{r.dataset}")
    return out


# -- building ---------------------------------------------------------------

def build(cfg: Config, config_path: Path | None = None, *, reason: str = "manual",
          runner: Runner = run_step, now: datetime | None = None) -> dict:
    r = cfg.release
    if r.site_dir is None:
        raise SystemExit("release.site_dir is not set in the config")
    now = now or utc_now()
    build_id = stamp(now)
    folder = r.releases_dir / build_id
    logs = folder / "logs"
    logs.mkdir(parents=True, exist_ok=False)
    previous = baseline(r.releases_dir)
    record = {"id": build_id, "started": iso(now), "reason": reason, "steps": [],
              "baseline": previous["id"] if previous else None}
    env = _env(config_path)
    with RunLock(r.releases_dir):
        for n, step in enumerate(steps(cfg, folder, build_id), 1):
            log = logs / f"{n:02d}-{step.name}.log"
            started = utc_now()
            code = runner(step, env, log)
            record["steps"].append({"name": step.name, "code": code, "seconds": int((utc_now() - started).total_seconds())})
            if code != 0:
                record.update(result="failed", failed_step=step.name, log_tail=_tail(log))
                break
        else:
            record["result"] = "ok"
            record["preview_url"] = _preview_url(logs)
            dist = folder / "dist"
            shutil.copytree(r.site_dir / "dist", dist)
            _write_sums(folder, ["outputs", "dist"])
            record["changes"] = changes(previous and r.releases_dir / previous["id"] / "outputs", folder / "outputs")
    record["finished"] = iso(utc_now())
    _write_json(folder / "release.json", record)
    report = render(record)
    (folder / "report.txt").write_text(report, encoding="utf-8")
    subject = (f"release {build_id} ready for review" if record["result"] == "ok"
               else f"ALERT: release {build_id} failed at {record['failed_step']}")
    record["report"] = notify(cfg, subject, report)
    _write_json(folder / "release.json", record)
    prune(r.releases_dir, r.keep)
    return record


def _tail(log: Path) -> list[str]:
    return log.read_text(encoding="utf-8", errors="replace").splitlines()[-LOG_TAIL:]


def _preview_url(logs: Path) -> str | None:
    for log in sorted(logs.glob("*-upload.log")):
        found = PREVIEW_URL.findall(log.read_text(encoding="utf-8", errors="replace"))
        if found:
            return found[-1]
    return None


def _write_sums(folder: Path, parts: list[str]) -> None:
    """SHA256SUMS of everything the build produced, in the format `sha256sum -c` reads."""
    lines = []
    for part in parts:
        for p in sorted((folder / part).rglob("*")):
            if p.is_file():
                lines.append(f"{sha256_file(p)}  {p.relative_to(folder).as_posix()}")
    (folder / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def changes(old: Path | None, new: Path) -> dict:
    """What the default setting's annual rates gained or revised since the previous release."""
    import duckdb

    new_rates = new / "gr" / "m1" / "m1_rates.parquet"
    if not new_rates.is_file():
        return {}
    con = duckdb.connect()
    default = ("spending = 'purchases' AND imputed_rent = 'excluded' AND price_source = 'cpi' "
               "AND weights_timing = 'N' AND tutoring = 'priced' AND unit = 'RCH_A'")
    keys = 'grouping, "group", coicop18, ref_period'
    n = f"SELECT {keys}, value_text FROM '{new_rates.as_posix()}' WHERE {default}"
    last = con.execute(f"SELECT max(ref_period) FROM ({n})").fetchone()[0]
    if old is None or not (old / "gr" / "m1" / "m1_rates.parquet").is_file():
        return {"first_release": True, "latest_period": last}
    o = f"SELECT {keys}, value_text FROM '{(old / 'gr' / 'm1' / 'm1_rates.parquet').as_posix()}' WHERE {default}"
    added = con.execute(f"SELECT count(*), list(DISTINCT a.ref_period ORDER BY a.ref_period) "
                        f"FROM ({n}) a ANTI JOIN ({o}) b USING (grouping, \"group\", coicop18, ref_period)").fetchone()
    revised = con.execute(f"""
        SELECT count(*), max(abs(TRY_CAST(a.value_text AS DOUBLE) - TRY_CAST(b.value_text AS DOUBLE)))
        FROM ({n}) a JOIN ({o}) b USING (grouping, "group", coicop18, ref_period)
        WHERE a.value_text IS DISTINCT FROM b.value_text""").fetchone()
    return {"latest_period": last, "new_values": added[0], "new_periods": added[1] or [],
            "revised_values": revised[0], "largest_revision_pp": revised[1]}


def render(record: dict) -> str:
    lines = [f"Release {record['id']} ({record['reason']}): {record['result'].upper()}", ""]
    for s in record["steps"]:
        lines.append(f"  {'ok  ' if s['code'] == 0 else 'FAIL'} {s['name']} ({s['seconds']} s)")
    if record["result"] == "ok":
        c = record.get("changes", {})
        lines += ["", f"Preview (private): {record.get('preview_url') or 'not found in the upload log'}", ""]
        if c.get("first_release"):
            lines.append(f"First release; latest month {c['latest_period']}.")
        elif c:
            lines += [f"Since release {record['baseline']} (default setting, annual rates):",
                      f"  latest month {c['latest_period']}; new months {', '.join(c['new_periods']) or 'none'}"
                      f" ({c['new_values']} values)",
                      f"  revised values: {c['revised_values']}"
                      + (f", largest {c['largest_revision_pp']:.1f} pp" if c["revised_values"] else "")]
        lines += ["", f"To publish it: traceconomics release promote {record['id']}"]
    else:
        lines += ["", f"Failed at {record['failed_step']}. Last lines of its log:", ""]
        lines += [f"  {line}" for line in record["log_tail"]]
    return "\n".join(lines) + "\n"


# -- promoting and listing ------------------------------------------------------

def baseline(releases_dir: Path) -> dict | None:
    """The build the next one is compared with: the promoted one, else the newest good one."""
    promoted = releases_dir / PROMOTED
    if promoted.is_file():
        return json.loads(promoted.read_text(encoding="utf-8"))
    good = [b for b in status(releases_dir) if b.get("result") == "ok"]
    return good[0] if good else None


def promote(cfg: Config, build_id: str, *, runner: Runner = run_step) -> dict:
    r = cfg.release
    folder = r.releases_dir / build_id
    record = json.loads((folder / "release.json").read_text(encoding="utf-8"))
    if record.get("result") != "ok":
        raise SystemExit(f"release {build_id} did not pass its checks; it can't be promoted")
    step = Step("promote", _wrangler(folder / "dist", r.pages_project, r.promote_branch), r.site_dir)
    log = folder / "logs" / f"promote-{stamp(utc_now())}.log"
    code = runner(step, _env(None), log)
    if code != 0:
        raise SystemExit(f"upload failed; see {log}")
    done = {"id": build_id, "branch": r.promote_branch, "promoted": iso(utc_now()),
            "url": _preview_url_in(log)}
    _write_json(r.releases_dir / PROMOTED, done)
    return done


def _preview_url_in(log: Path) -> str | None:
    found = PREVIEW_URL.findall(log.read_text(encoding="utf-8", errors="replace"))
    return found[-1] if found else None


def status(releases_dir: Path) -> list[dict]:
    """Every build, newest first."""
    out = []
    for f in sorted(releases_dir.glob("*/release.json"), reverse=True):
        rec = json.loads(f.read_text(encoding="utf-8"))
        out.append({k: rec.get(k) for k in ("id", "result", "reason", "failed_step", "preview_url")})
    return out


def prune(releases_dir: Path, keep: int) -> list[str]:
    """Delete all but the newest `keep` builds; the promoted build is always kept."""
    promoted = baseline(releases_dir) if (releases_dir / PROMOTED).is_file() else None
    builds = sorted((p for p in releases_dir.iterdir() if (p / "release.json").is_file()), reverse=True)
    gone = []
    for p in builds[keep:]:
        if promoted and p.name == promoted["id"]:
            continue
        shutil.rmtree(p)
        gone.append(p.name)
    return gone
