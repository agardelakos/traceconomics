"""Building a release: everything after the archive job, up to a private preview of the site.

`build` runs the steps below in order and stops at the first failure: update the store, compute
every series and the error bands, run the checks, write the site's data, build and test the
site, open its pages in a browser, upload it as a preview, and open the preview's pages in a
browser again (there the host's real headers apply). Each build gets a folder (`<releases>/<id>/`)
with every step's log, the outputs, the built site, checksums of both and a report, which is
emailed with the preview link and what changed since the last release.

A build held back by its browser tests (or its upload) can be tested again with `retest`, after a
network fault or a slow host: the same tests, on the same built files. A test or a page that was
wrong needs a new build instead, which `retest` enforces by refusing when the tests changed.

The site is hosted as static files on Cloudflare Workers. An upload creates a version with its own
preview address and leaves the live site as it is. Nothing reaches the public address until the
owner looks at the preview and promotes the build (`promote`): a person checks every release
before it is published. Each promote names its target: `staging`, a private preview alias that
stays after launch as a place to look at a build in its final setting, or `production`, the
public address. The two can serve different builds, so a rollback is per target too. After each
promote, the target address is checked: it must serve the promoted build's own files.

With `[release] auto_promote` on, a passing build whose only change is the publishers' new data,
within its limits, is promoted to production by itself; any other build waits for the owner, with
the reasons (`release_decision.py`). In "shadow" the email only says what would have happened.

Each browser step's results, and each promote's check, are also sent to the test-results bucket
(`testresults`), for the project's public run history. That is a report, not a gate: a failed
upload is named in the email and changes nothing else.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from traceconomics import catalog, quoted_figures, release_decision as rd, testresults
from traceconomics.archive.store import Archive, iso, sha256_file, stamp, utc_now
from traceconomics.config import CONFIG_ENV, Config
from traceconomics.job import Locked, RunLock
from traceconomics.notify import notify

PROMOTED = "promoted.json"
# A build asked for while another ran (`build`): started when that one ends.
WANTED = "build-wanted.json"
PREVIEW_URL = re.compile(r"https://[\w.-]+\.workers\.dev\b[^\s\"']*")
# Promoting to production publishes on the site's public address; staging is a private preview alias.
STAGING, PRODUCTION = "staging", "production"
TARGETS = (STAGING, PRODUCTION)
LOG_TAIL = 40
# Stands in a step's environment for the build's preview address, known only once uploaded.
PREVIEW = "<preview address>"
# The steps a held-back build can run again (`retest`).
RETESTABLE = ("ui-test", "upload", "smoke")
# Every build's copy differs (it records when it was generated): the file that tells builds apart.
METADATA = "data/v1/gr/m1/latest/metadata.json"
# A new version takes a moment to reach every location of the host. Both are assumptions, to
# adjust once measured: ask every 10 seconds, give up after 2 minutes.
CONFIRM_EVERY, CONFIRM_FOR = 10, 120


@dataclass(frozen=True)
class Step:
    """One command of a release build: its name, arguments, working folder and extra environment."""

    name: str
    argv: tuple[str, ...]
    cwd: Path | None = None
    env: tuple[tuple[str, str], ...] = ()


# A runner executes one step, writing its output to the log file, and returns the exit code.
Runner = Callable[[Step, dict, Path], int]


def run_step(step: Step, env: dict, log: Path) -> int:
    """Run a step with its output and errors written to the log file, and return its exit code."""
    exe = shutil.which(step.argv[0]) or step.argv[0]  # npm and npx are .cmd files on Windows
    with log.open("w", encoding="utf-8") as f:
        f.write(f"$ {' '.join(step.argv)}\n")
        f.flush()
        return subprocess.run(
            [exe, *step.argv[1:]], cwd=step.cwd, env=env, stdout=f, stderr=subprocess.STDOUT
        ).returncode


def _py(*args: str) -> tuple[str, ...]:
    return (sys.executable, "-I", "-m", "traceconomics", *args)


def steps(cfg: Config, folder: Path, build_id: str, ui: Path | None = None) -> list[Step]:
    """`ui`: where the browser tests keep their reports and traces (default `<build>/ui`)."""
    r = cfg.release
    site, outputs, ui = r.site_dir, folder / "outputs", ui or folder / "ui"
    return [
        # Our survey tables must match the code and the files they were built from: a build on
        # stale tables is wrong, not just unreviewed, so it stops here (refuse, don't guess).
        Step("inputs", _py("check", "inputs")),
        Step("store", _py("store", "update")),
        Step("series", _py("module1", "run", "--out", str(outputs), "--combinations", "all")),
        Step("bands", _py("bands", "run", "--combinations", "all", "--replicates", str(r.replicates))),
        Step("store-bands", _py("store", "update")),
        Step("check-v1", _py("check", "v1")),
        Step("check-v1-cpi", _py("check", "v1-cpi")),
        Step("check-combos", _py("check", "combos", "--outputs", str(outputs))),
        # Our own weights switch (a new year, a new survey year): nothing published shows it, so
        # the outputs are checked against rule N here.
        Step("check-weights", _py("check", "weights", "--outputs", str(outputs))),
        # Each official figure against its own inputs. Differences never fail it (they are what the
        # topic publishes); only an input it can't read does.
        Step("consistency", _py("module5", "run", "--out", str(outputs))),
        Step("export", _py("export", "site", "--out", str(site / "public" / "data"), "--outputs", str(outputs))),
        # Past figures typed into the text, against the data just exported: a revision that
        # changes one stops the build, since nobody may read the text before it goes live.
        Step(
            "check-figures",
            _py(
                "check",
                "figures",
                "--data",
                str(site / "public" / "data"),
                "--allow",
                str(site / "src" / "i18n" / "figures-allow.json"),
            ),
        ),
        Step("npm-ci", ("npm", "ci", "--no-audit", "--no-fund"), site),
        Step("site-check", ("npm", "run", "check"), site),
        # The built pages in a browser, on a local server, before anything leaves this machine.
        Step("ui-test", ("npm", "run", "test:ui"), site, _ui_env(ui / "ui-test")),
        Step("upload", _upload(site / "dist", r.worker_name, f"build-{build_id.lower()}", build_id), site),
        # The short set (tests tagged @smoke) on the uploaded preview: what the host really serves,
        # headers included. The full suite already ran on the same files in ui-test.
        Step(
            "smoke",
            ("npm", "run", "test:ui", "--", "--grep", "@smoke"),
            site,
            (("BASE_URL", PREVIEW), *_ui_env(ui / "smoke")),
        ),
    ]


def _ui_env(folder: Path) -> tuple[tuple[str, str], ...]:
    return (
        ("UI_OUTPUT", str(folder / "results")),
        ("UI_REPORT", str(folder / "report")),
        ("UI_JSON", str(folder / "results.json")),
    )


BROWSER_STEPS = ("ui-test", "smoke")


def ui_failures(results: Path) -> list[str]:
    """The failed tests and outside errors in a Playwright results file, one line each.

    Each failed test as "<test>: <first line of its error>", and errors outside any test (a
    server that didn't start); [] if the file is missing or unreadable.
    """
    try:
        data = json.loads(results.read_text(encoding="utf-8"))
    except OSError, ValueError:
        return []
    out = []

    def first(text) -> str:
        lines = [x.strip() for x in re.sub(r"\x1b\[[0-9;]*m", "", str(text or "")).splitlines() if x.strip()]
        return lines[0][:200] if lines else ""

    def walk(suite: dict, path: list[str]) -> None:
        for spec in suite.get("specs", []):
            for t in spec.get("tests", []):
                if t.get("status") in ("unexpected", "flaky"):
                    error = next((r["error"].get("message") for r in t.get("results", []) if r.get("error")), "")
                    out.append(f"{' › '.join(x for x in [*path, spec.get('title', '')] if x)}: {first(error)}")
        for s in suite.get("suites", []):
            walk(s, [*path, s.get("title", "")])

    for s in data.get("suites", []):
        walk(s, [s.get("title", "")])  # the top level is the test file
    out += [f"(outside the tests): {first(e.get('message'))}" for e in data.get("errors", [])]
    return out


def _note_ui(record: dict, ui: Path, step: str) -> None:
    """After a failed browser step: which tests failed, and where their report is."""
    if step in BROWSER_STEPS:
        record["ui_failures"] = ui_failures(ui / step / "results.json")
        record["ui_report"] = str(ui / step / "report" / "index.html")


def ui_fingerprint(site: Path) -> str:
    """The browser tests as they are: their files, their config, and the lock file that pins Playwright.

    A retest must run the tests its build ran.
    """
    files = [site / "playwright.config.ts", site / "package-lock.json", *sorted((site / "tests" / "ui").rglob("*"))]
    h = hashlib.sha256()
    for f in files:
        if f.is_file():
            h.update(f.relative_to(site).as_posix().encode() + b"\0")
            h.update(f.read_bytes().replace(b"\r\n", b"\n") + b"\0")
    return h.hexdigest()[:16]


def _upload(folder: Path, name: str, alias: str, message: str) -> tuple[str, ...]:
    """A new version with a preview address (`<alias>-<name>.<subdomain>.workers.dev`); the live site is untouched."""
    return (
        "npx",
        "--no-install",
        "wrangler",
        "versions",
        "upload",
        "--assets",
        str(folder),
        "--name",
        name,
        "--preview-alias",
        alias,
        "--message",
        message,
    )


def _publish(folder: Path, name: str, message: str) -> tuple[str, ...]:
    """Upload and make live on the public address."""
    return ("npx", "--no-install", "wrangler", "deploy", "--assets", str(folder), "--name", name, "--message", message)


def _env(config_path: Path | None) -> dict:
    env = dict(os.environ)
    if config_path is not None:
        env[CONFIG_ENV] = str(config_path)
    env.setdefault("WRANGLER_SEND_METRICS", "false")
    # Release builds carry the visit-count beacon; local builds and tests don't (site/src/lib/analytics.ts).
    env["TRACECONOMICS_ANALYTICS"] = "on"
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


def build(
    cfg: Config,
    config_path: Path | None = None,
    *,
    reason: str = "manual",
    runner: Runner = run_step,
    now: datetime | None = None,
    released: datetime | None = None,
) -> dict:
    """Build, check and test a release.

    `released` is when the publisher released the data it was started for (the job passes it),
    so the record can say how long the data took to go live.

    One build at a time. A build that finds another running doesn't fail: it is queued
    (`WANTED`), and the running build starts it when it ends, so new files never wait for the
    next release day. Then the record is {"id": None, "result": "queued", ...}."""
    r = cfg.release
    if r.site_dir is None:
        raise SystemExit("release.site_dir is not set in the config")
    try:
        lock = RunLock(r.releases_dir).__enter__()
    except Locked:
        want(r.releases_dir, reason, released)
        return {"id": None, "result": "queued", "reason": reason}
    try:
        record, folder = _build(cfg, config_path, reason, runner, now or utc_now(), released)
    finally:
        lock.__exit__(None, None, None)
    if record["result"] == "ok" and r.auto_promote != rd.OFF:
        _auto_promote(cfg, folder, record, runner)
    record["finished"] = iso(utc_now())
    _report(cfg, folder, record, email_subject(record))
    prune(r.releases_dir, r.keep)
    wanted = take_wanted(r.releases_dir)
    if wanted:
        nxt = build(cfg, config_path, reason=wanted["reason"], runner=runner, released=wanted["released"])
        record["next"] = nxt["id"]
    return record


def _build(
    cfg: Config, config_path: Path | None, reason: str, runner: Runner, now: datetime, released: datetime | None
) -> tuple[dict, Path]:
    """The build's steps, under the lock."""
    r = cfg.release
    build_id = stamp(now)
    folder = r.releases_dir / build_id
    logs = folder / "logs"
    logs.mkdir(parents=True, exist_ok=False)
    previous = baseline(r.releases_dir)
    record = {
        "id": build_id,
        "started": iso(now),
        "reason": reason,
        "steps": [],
        "baseline": previous["id"] if previous else None,
        "ui_fingerprint": ui_fingerprint(r.site_dir),
        # Kept with the build: a retest or a promote after a later deploy still reports this one.
        "commit": testresults.source_commit(r.site_dir.parent),
    }
    if released is not None:
        record["released"] = iso(released)
    failed = _run_steps(
        steps(cfg, folder, build_id),
        _env(config_path),
        logs,
        logs,
        runner,
        record["steps"],
        after={"site-check": lambda: shutil.copytree(r.site_dir / "dist", folder / "dist")},
        on_browser=_send_results(record),
    )
    if failed:
        record.update(result="failed", failed_step=failed[0], log_tail=failed[1])
        _note_ui(record, folder / "ui", failed[0])
    else:
        _passed(cfg, folder, record)
        record["ready"] = iso(utc_now())
    return record, folder


def want(releases_dir: Path, reason: str, released: datetime | None) -> None:
    """Queue a build for when the running one ends.

    Several wishes make one build: their reasons together, timed from the earliest release among
    them (the data that has waited longest).
    """
    path = releases_dir / WANTED
    old = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {"reasons": [], "released": None}
    reasons = old["reasons"] + ([reason] if reason not in old["reasons"] else [])
    times = [t for t in (old["released"], released and iso(released)) if t]
    _write_json(path, {"reasons": reasons, "released": min(times) if times else None})


def take_wanted(releases_dir: Path) -> dict | None:
    """The queued build's reason and release time, removing the wish; None if none is queued."""
    path = releases_dir / WANTED
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    path.unlink()
    released = datetime.fromisoformat(data["released"]) if data["released"] else None
    return {"reason": "queued while another build ran: " + "; ".join(data["reasons"]), "released": released}


def _auto_promote(cfg: Config, folder: Path, record: dict, runner: Runner) -> None:
    """Decide; in "on" mode, promote a build the decision allows."""
    r = cfg.release
    decision = decide_build(cfg, folder, record)
    record["decision"] = {**decision.as_dict(), "mode": r.auto_promote}
    if r.auto_promote == rd.ON and decision.verdict == rd.PROMOTE:
        _write_json(folder / "release.json", record)  # promote reads the build's record from disk
        try:
            done = promote(cfg, record["id"], PRODUCTION, runner=runner)
            record["decision"]["promoted"] = done
            if "live" in done:
                record["live"] = done["live"]
        except SystemExit as exc:
            record["decision"]["promote_failed"] = str(exc)


def email_subject(record: dict) -> str:
    """The email's subject: what happened, and whether the owner has to act."""
    build_id = record["id"]
    if record["result"] != "ok":
        return f"ALERT: release {build_id} failed at {record['failed_step']}"
    d = record.get("decision")
    if not d:
        return f"release {build_id} ready for review"
    first = "; ".join(d["reasons"][:2]) + (f" (and {len(d['reasons']) - 2} more)" if len(d["reasons"]) > 2 else "")
    if d["mode"] == rd.SHADOW:
        would = "would promote" if d["verdict"] == rd.PROMOTE else f"would hold: {first}"
        return f"release {build_id} ready for review (shadow: {would})"
    if d.get("promote_failed"):
        return f"ALERT: release {build_id} was to go live by itself, but its promote failed"
    if d.get("promoted"):
        return f"PROMOTED: release {build_id} is live (only the publishers' data changed)"
    return f"HOLD: release {build_id} waits for you: {first}"


def decide_build(cfg: Config, folder: Path, record: dict, *, fetch=None) -> rd.Decision:
    """The decision for a passing build, against the build production serves (`release_decision`)."""
    r = cfg.release
    on = promoted(r.releases_dir).get(PRODUCTION)
    if not on:
        return rd.decide(
            production=None,
            commit=None,
            production_commit=None,
            inputs=None,
            production_inputs=None,
            changes={},
            beyond=[],
            served_problem=None,
        )
    prod = r.releases_dir / on["id"]
    if not (prod / "release.json").is_file():
        return rd.Decision(rd.HOLD, [f"production's build {on['id']} is no longer on disk"], on["id"])
    prod_record = json.loads((prod / "release.json").read_text(encoding="utf-8"))
    # One look at the public address, no waiting: it must serve the production build's own file.
    served = confirm(
        r.production_url,
        (prod / "dist" / METADATA).read_bytes(),
        on["id"],
        fetch=fetch or (lambda u: _fetch(u, cfg.user_agent)),
        sleep=lambda _: None,
        every=1,
        limit=0,
    )
    rates = Path("gr") / "m1" / "m1_rates.parquet"
    old_rates, new_rates = prod / "outputs" / rates, folder / "outputs" / rates
    both = old_rates.is_file() and new_rates.is_file()
    allow = r.site_dir / "src" / "i18n" / "figures-allow.json"
    quoted = quoted_figures.sources(quoted_figures.load(allow)) if allow.is_file() else {}
    return rd.decide(
        production=on["id"],
        quoted=quoted,
        commit=record.get("commit"),
        production_commit=prod_record.get("commit"),
        inputs=_inputs(folder),
        production_inputs=_inputs(prod),
        changes=changes(prod / "outputs", folder / "outputs") if both else {},
        beyond=rd.beyond_records_in(old_rates, new_rates) if both else [],
        served_problem=served,
    )


def _inputs(folder: Path) -> dict | None:
    path = folder / rd.INPUTS
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def _run_steps(
    todo: list[Step],
    env: dict,
    logs: Path,
    step_logs: Path,
    runner: Runner,
    ran: list,
    after: dict | None = None,
    on_browser: Callable | None = None,
) -> tuple[str, list[str]] | None:
    """Run the steps in order, each logged in `step_logs`; None, or (failed step, its log's last lines).
    `logs`: the build's log folder, where the preview address is looked up. `after`: step name ->
    what to do once that step has passed. `on_browser(step, started, code, results)`: after each
    browser step, passed or not."""
    for n, step in enumerate(todo, 1):
        log = step_logs / f"{n:02d}-{step.name}.log"
        started = utc_now()
        step_env = _step_env(step, env, logs)
        if step_env is None:
            log.write_text(f"{step.name}: no preview address in the upload log\n", encoding="utf-8")
            code = 1
        else:
            code = runner(step, step_env, log)
        ran.append({"name": step.name, "code": code, "seconds": int((utc_now() - started).total_seconds())})
        if on_browser and step.name in BROWSER_STEPS and step_env is not None:
            on_browser(step.name, started, code, Path(step_env["UI_JSON"]))
        if code != 0:
            return step.name, _tail(log)
        if after and step.name in after:
            after[step.name]()
    return None


def _send_results(record: dict) -> Callable:
    """After a browser step: send its results to the test-results bucket, noting the outcome in the
    build record. A step that never wrote a results file (it couldn't start) sends nothing."""

    def send(step: str, started: datetime, code: int, results: Path) -> None:
        if not results.is_file():
            return
        out = testresults.send(
            build=record["id"],
            commit=record.get("commit"),
            step=step,
            started=started,
            result="passed" if code == 0 else "failed",
            results=results,
        )
        if out["result"] != "off":
            record.setdefault("test_results", []).append({"step": step, **out})

    return send


def _step_env(step: Step, env: dict, logs: Path) -> dict | None:
    out = dict(env)
    for key, value in step.env:
        if value == PREVIEW:
            value = _preview_url(logs)
            if value is None:
                return None
        out[key] = value
    return out


def _passed(cfg: Config, folder: Path, record: dict) -> None:
    """Fill in a build that has passed every step."""
    r = cfg.release
    record.update(result="ok", preview_url=_preview_url(folder / "logs"))
    for key in ("failed_step", "log_tail", "ui_failures", "ui_report"):
        record.pop(key, None)
    _write_sums(folder, ["outputs", "dist"])
    # Every archived file the store held for this build: what an automatic promote compares.
    _write_json(folder / rd.INPUTS, rd.store_inputs(cfg.store_dir))
    previous = record.get("baseline")
    record["changes"] = changes(previous and r.releases_dir / previous / "outputs", folder / "outputs")


def _report(cfg: Config, folder: Path, record: dict, subject: str) -> None:
    _write_json(folder / "release.json", record)
    report = render(record)
    (folder / "report.txt").write_text(report, encoding="utf-8", newline="\n")
    record["report"] = notify(cfg, subject, report)
    _write_json(folder / "release.json", record)


def retest(
    cfg: Config,
    build_id: str,
    config_path: Path | None = None,
    *,
    runner: Runner = run_step,
    now: datetime | None = None,
) -> dict:
    """Run a held-back build's browser tests again on the files it built.

    Its upload runs again too if it never got that far. A pass makes it a good build, ready to
    promote.
    """
    r = cfg.release
    if r.site_dir is None:
        raise SystemExit("release.site_dir is not set in the config")
    folder = r.releases_dir / build_id
    if not (folder / "release.json").is_file():
        raise SystemExit(f"no release {build_id}; see `traceconomics release status`")
    record = json.loads((folder / "release.json").read_text(encoding="utf-8"))
    if record.get("result") == "ok":
        raise SystemExit(f"release {build_id} already passed its checks")
    if record.get("failed_step") not in RETESTABLE:
        raise SystemExit(
            f"release {build_id} failed at {record.get('failed_step')}: only a build held back at "
            f"{', '.join(RETESTABLE)} can be retested; build again"
        )
    if record.get("ui_fingerprint") != ui_fingerprint(r.site_dir):
        raise SystemExit(f"the browser tests here are not the ones release {build_id} was built with: build again")
    now = now or utc_now()
    tag = f"retest-{stamp(now)}"
    logs = folder / "logs"
    (logs / tag).mkdir(parents=True)
    attempt = {"started": iso(now), "steps": []}
    with RunLock(r.releases_dir):
        # The local test serves the site folder's dist/: put this build's own files there.
        dist = r.site_dir / "dist"
        if dist.exists():
            shutil.rmtree(dist)
        shutil.copytree(folder / "dist", dist)
        todo = [s for s in steps(cfg, folder, build_id, ui=folder / "ui" / tag) if s.name in RETESTABLE]
        if _preview_url(logs):
            todo = [s for s in todo if s.name != "upload"]  # uploaded already: test that version
        failed = _run_steps(
            todo, _env(config_path), logs, logs / tag, runner, attempt["steps"], on_browser=_send_results(record)
        )
    attempt["result"] = "failed" if failed else "ok"
    attempt["finished"] = iso(utc_now())
    record.setdefault("retests", []).append(attempt)
    if failed:
        record.update(failed_step=failed[0], log_tail=failed[1])
        _note_ui(record, folder / "ui" / tag, failed[0])
        subject = f"ALERT: release {build_id} failed its retest at {failed[0]}"
    else:
        _passed(cfg, folder, record)
        record["ready"] = iso(utc_now())  # a retest's delay counts: the data waited for it
        subject = f"release {build_id} passed its retest: ready for review"
    _report(cfg, folder, record, subject)
    return record


def _tail(log: Path) -> list[str]:
    return log.read_text(encoding="utf-8", errors="replace").splitlines()[-LOG_TAIL:]


def _preview_url(logs: Path) -> str | None:
    # A retest that uploads logs into its own subfolder.
    for log in sorted(logs.rglob("*-upload.log")):
        if url := _url_in(log):
            return url
    return None


def _write_sums(folder: Path, parts: list[str]) -> None:
    """SHA256SUMS of everything the build produced, in the format `sha256sum -c` reads."""
    lines = []
    for part in parts:
        for p in sorted((folder / part).rglob("*")):
            if p.is_file():
                lines.append(f"{sha256_file(p)}  {p.relative_to(folder).as_posix()}")
    (folder / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8", newline="\n")


def changes(old: Path | None, new: Path) -> dict:
    """What the default setting's annual rates gained or revised since the previous release."""
    import duckdb

    new_rates = new / "gr" / "m1" / "m1_rates.parquet"
    if not new_rates.is_file():
        return {}
    con = duckdb.connect()
    default = rd.DEFAULT_SETTING
    keys = 'grouping, "group", coicop18, ref_period'
    n = f"SELECT {keys}, value_text FROM '{new_rates.as_posix()}' WHERE {default}"
    last = con.execute(f"SELECT max(ref_period) FROM ({n})").fetchone()[0]
    if old is None or not (old / "gr" / "m1" / "m1_rates.parquet").is_file():
        return {"first_release": True, "latest_period": last}
    o = f"SELECT {keys}, value_text FROM '{(old / 'gr' / 'm1' / 'm1_rates.parquet').as_posix()}' WHERE {default}"
    added = con.execute(
        f"SELECT count(*), list(DISTINCT a.ref_period ORDER BY a.ref_period) "
        f'FROM ({n}) a ANTI JOIN ({o}) b USING (grouping, "group", coicop18, ref_period)'
    ).fetchone()
    revised = con.execute(f"""
        SELECT count(*), max(abs(TRY_CAST(a.value_text AS DOUBLE) - TRY_CAST(b.value_text AS DOUBLE)))
        FROM ({n}) a JOIN ({o}) b USING (grouping, "group", coicop18, ref_period)
        WHERE a.value_text IS DISTINCT FROM b.value_text""").fetchone()
    return {
        "latest_period": last,
        "new_values": added[0],
        "new_periods": added[1] or [],
        "revised_values": revised[0],
        "largest_revision_pp": revised[1],
    }


def _seconds(start: str, end: str) -> int:
    return round((datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds())


def duration(seconds: int) -> str:
    """Like "2 h 05 min" or "47 min": a release's time to go live, as the email gives it."""
    hours, minutes = divmod(round(seconds / 60), 60)
    return f"{hours} h {minutes:02d} min" if hours else f"{minutes} min"


def _timing(record: dict) -> list[str]:
    """Release to ready, and to live once production serves the build."""
    released = record.get("released")
    if not released or "ready" not in record:
        return []
    lines = [f"Released by the publisher {released}; build ready after {duration(_seconds(released, record['ready']))}"]
    if "live" in record:
        lines[0] += f", live after {duration(record['live']['seconds'])}"
    return lines + [""]


def render(record: dict) -> str:
    """The text of a release build's report: its steps, retests, changes and decision, or why it failed."""
    lines = [f"Release {record['id']} ({record['reason']}): {record['result'].upper()}", ""]
    lines += _timing(record)
    for s in record["steps"]:
        lines.append(f"  {'ok  ' if s['code'] == 0 else 'FAIL'} {s['name']} ({s['seconds']} s)")
    for a in record.get("retests", []):
        lines += ["", f"Retest {a['started']}: {a['result'].upper()}"]
        lines += [f"  {'ok  ' if s['code'] == 0 else 'FAIL'} {s['name']} ({s['seconds']} s)" for s in a["steps"]]
    unsent = [x for x in record.get("test_results", []) if x["result"] != "ok"]
    if unsent:
        lines += ["", "Test results not sent to the run history (the build is not affected):"]
        lines += [f"  - {x['step']}: {x.get('error', 'failed')}" for x in unsent]
    if record["result"] == "ok":
        c = record.get("changes", {})
        lines += ["", f"Preview (private): {record.get('preview_url') or 'not found in the upload log'}", ""]
        if c.get("first_release"):
            lines.append(f"First release; latest month {c['latest_period']}.")
        elif c:
            lines += [
                f"Since release {record['baseline']} (default setting, annual rates):",
                f"  latest month {c['latest_period']}; new months {', '.join(c['new_periods']) or 'none'}"
                f" ({c['new_values']} values)",
                f"  revised values: {c['revised_values']}"
                + (f", largest {c['largest_revision_pp']:.1f} pp" if c["revised_values"] else ""),
            ]
        lines += _render_decision(record)
        if not record.get("decision", {}).get("promoted"):
            lines += [
                "",
                f"To publish it: traceconomics release promote {record['id']} --to staging (or --to production)",
            ]
    else:
        lines += ["", "Nothing was published: staging and the public site are unchanged."]
        if "ui_failures" in record:
            lines += ["", "Failing browser tests:"]
            lines += [f"  - {f}" for f in record["ui_failures"] or ["(none named: see the log)"]]
            lines += [f"Report (screenshots, console errors, traces): {record['ui_report']}"]
        lines += ["", f"Failed at {record['failed_step']}. Last lines of its log:", ""]
        lines += [f"  {line}" for line in record["log_tail"]]
        if record["failed_step"] in RETESTABLE:
            lines += [
                "",
                "If the cause was passing (the network, the host), test it again: "
                f"traceconomics release retest {record['id']}. If a test or a page was wrong, fix it and build again.",
            ]
    return "\n".join(lines) + "\n"


def _render_decision(record: dict) -> list[str]:
    d = record.get("decision")
    if not d:
        return []
    title = {rd.SHADOW: "Automatic promote (shadow: nothing was promoted)", rd.ON: "Automatic promote"}[d["mode"]]
    lines = ["", f"{title}, against production's build {d.get('production') or 'none'}:"]
    if d["verdict"] == rd.PROMOTE:
        lines.append("  promote: only the publishers' data changed, within every limit")
    else:
        lines.append("  hold, because:")
        lines += [f"  - {x}" for x in d["reasons"]]
    done = d.get("promoted")
    if done:
        lines += [
            "",
            f"Promoted to production: {done['url']} serves it (checked {done.get('confirmed')}).",
        ]
        if done.get("previous"):
            lines.append(
                f"Live before: {done['previous']}. To go back: "
                f"traceconomics release promote {done['previous']} --to production"
            )
    if d.get("promote_failed"):
        lines += ["", f"The promote failed: {d['promote_failed']}"]
    return lines


# -- promoting and listing ------------------------------------------------------


def promoted(releases_dir: Path) -> dict[str, dict]:
    """What each target serves now: {target: {id, to, promoted, url}}."""
    path = releases_dir / PROMOTED
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    # Written before promotes named a target: one record, for the only target there was.
    return {data["to"]: data} if "id" in data else data


def baseline(releases_dir: Path) -> dict | None:
    """The build the next one is compared with.

    The one on production, else on staging, else the newest good one.
    """
    on = promoted(releases_dir)
    if on:
        return on.get(PRODUCTION) or on[STAGING]
    good = [b for b in status(releases_dir) if b.get("result") == "ok"]
    return good[0] if good else None


def promote(cfg: Config, build_id: str, to: str, *, runner: Runner = run_step, fetch=None, sleep=time.sleep) -> dict:
    """Make a good build live on `to`, then check that the target serves it (`confirm`)."""
    if to not in TARGETS:
        raise SystemExit(f"promote to {' or '.join(TARGETS)}, not {to!r}")
    r = cfg.release
    if to == PRODUCTION and not r.production_url:
        raise SystemExit("release.production_url is not set in the config: the promote couldn't be checked")
    folder = r.releases_dir / build_id
    record = json.loads((folder / "release.json").read_text(encoding="utf-8"))
    if record.get("result") != "ok":
        raise SystemExit(f"release {build_id} did not pass its checks; it can't be promoted")
    argv = (
        _publish(folder / "dist", r.worker_name, build_id)
        if to == PRODUCTION
        else _upload(folder / "dist", r.worker_name, to, build_id)
    )
    step = Step("promote", argv, r.site_dir)
    log = folder / "logs" / f"promote-{to}-{stamp(utc_now())}.log"
    code = runner(step, _env(None), log)
    if code != 0:
        raise SystemExit(f"upload failed; see {log}")
    url = r.production_url if to == PRODUCTION else _url_in(log)
    done = {"id": build_id, "to": to, "promoted": iso(utc_now()), "url": url}
    # The build this one replaces on the target: kept on disk (`prune`) so a revert has it.
    before = promoted(r.releases_dir).get(to)
    if before:
        done["previous"] = before["id"] if before["id"] != build_id else before.get("previous")
    checked = utc_now()
    problem = confirm(
        url,
        (folder / "dist" / METADATA).read_bytes(),
        build_id,
        fetch=fetch or (lambda u: _fetch(u, cfg.user_agent)),
        sleep=sleep,
    )
    done["confirmed" if problem is None else "unconfirmed"] = iso(utc_now()) if problem is None else problem
    if problem is None and to == PRODUCTION and record.get("released"):
        # The number the speed work is judged by: from the publisher's release to our site serving it.
        done["live"] = {"at": done["confirmed"], "seconds": _seconds(record["released"], done["confirmed"])}
        _write_json(folder / "release.json", {**record, "live": done["live"]})
    sent = testresults.send(
        build=build_id,
        commit=record.get("commit"),
        step="promote",
        started=checked,
        result="passed" if problem is None else "failed",
    )
    if sent["result"] != "off":
        done["test_results"] = sent
    _write_json(r.releases_dir / PROMOTED, {**promoted(r.releases_dir), to: done})
    if problem is not None:
        raise SystemExit(
            f"promoted {build_id} to {to}, but {url or 'its address'} doesn't serve it ({problem}). "
            "Look at the address, then promote again or revert to the previous build."
        )
    return done


def confirm(
    url: str | None,
    expected: bytes,
    build_id: str,
    *,
    fetch,
    sleep,
    every: int = CONFIRM_EVERY,
    limit: int = CONFIRM_FOR,
) -> str | None:
    """None once `url` serves the build's own `metadata.json` (byte for byte), else what was last seen."""
    if not url:
        return "no address to check"
    last = "no answer"
    for attempt in range(limit // every + 1):
        if attempt:
            sleep(every)
        try:
            # The query string keeps any cache from answering with an older copy.
            if fetch(f"{url.rstrip('/')}/{METADATA}?promote={build_id}") == expected:
                return None
            last = f"after {attempt * every} s it still serves another build"
        except OSError as e:  # includes HTTP errors and timeouts
            last = f"{type(e).__name__}: {e}"
    return last


def _fetch(url: str, user_agent: str) -> bytes:
    # Our own user agent, as for every fetch: the host turns away Python's default one (403).
    headers = {"User-Agent": user_agent, "Cache-Control": "no-cache"}
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=20) as f:
        return f.read()


def _url_in(log: Path) -> str | None:
    """The address in an upload log. Wrangler prints the version's own preview address and, when
    an alias was given, the alias address too (stable across uploads): the alias is preferred."""
    text = log.read_text(encoding="utf-8", errors="replace")
    aliased = [u for line in text.splitlines() if "alias" in line.lower() for u in PREVIEW_URL.findall(line)]
    found = PREVIEW_URL.findall(text)
    return (aliased or found or [None])[-1]


def status(releases_dir: Path) -> list[dict]:
    """Every build, newest first, with the targets it is on."""
    on = promoted(releases_dir)
    out = []
    for f in sorted(releases_dir.glob("*/release.json"), reverse=True):
        rec = json.loads(f.read_text(encoding="utf-8"))
        row = {k: rec.get(k) for k in ("id", "result", "reason", "failed_step", "preview_url")}
        row["on"] = [t for t in TARGETS if on.get(t, {}).get("id") == rec.get("id")]
        out.append(row)
    return out


def prune(releases_dir: Path, keep: int) -> list[str]:
    """Delete all but the newest `keep` builds.

    A build on staging or production, and the one each replaced there (the revert target), is
    always kept.
    """
    on = promoted(releases_dir).values()
    live = {rec["id"] for rec in on} | {rec["previous"] for rec in on if rec.get("previous")}
    builds = sorted((p for p in releases_dir.iterdir() if (p / "release.json").is_file()), reverse=True)
    gone = []
    for p in builds[keep:]:
        if p.name in live:
            continue
        shutil.rmtree(p)
        gone.append(p.name)
    return gone
