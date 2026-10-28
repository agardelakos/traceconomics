"""The archive job: decide whether a run is due, run the sources, report.

The job is meant to be triggered every day (e.g. by Windows Task Scheduler)
and to do real work only when a release has happened since the last good
run: ELSTAT and Eurostat both publish at 12:00 Greek time, and the job runs
from 13:00. A day the computer was off is caught up at the next trigger and
reported as missed. A run with failures doesn't count as good, so the next
trigger tries again.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from traceconomics import analytics, backup, heartbeat
from traceconomics.archive.store import Archive, iso, utc_now
from traceconomics.config import Config
from traceconomics.notify import notify
from traceconomics.sources import elstat, eurostat, terms
from traceconomics.sources.elstat import history as elstat_history
from traceconomics.sources.base import HttpClient, RunContext

STATE_FILE = "state/state.json"
LOCK_FILE = "state/run.lock"
STALE_LOCK = timedelta(hours=6)
# Cloudflare keeps exact visit-count rows for 7 days: alert while there are still a few left.
ANALYTICS_ALERT_DAYS = 4


# -- state (a rebuildable cache next to the archive) ------------------------

def load_state(root: Path) -> dict:
    path = root / STATE_FILE
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_state(root: Path, state: dict) -> None:
    path = root / STATE_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".part")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)


class Locked(Exception):
    pass


class RunLock:
    """Stops two runs (say, a scheduled and a manual one) from writing at once."""

    def __init__(self, root: Path):
        self.path = root / LOCK_FILE

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            age = datetime.now().timestamp() - self.path.stat().st_mtime
            if age < STALE_LOCK.total_seconds():
                raise Locked(f"another run holds {self.path}")
            self.path.unlink()
        fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        return self

    def __exit__(self, *exc):
        self.path.unlink(missing_ok=True)


# -- when to run ------------------------------------------------------------

@dataclass(frozen=True)
class Due:
    due: bool
    release_days: list[date]  # release days since the last good run
    missed: list[date]        # of those, days with no run on the day itself
    reason: str


def all_release_dates(state: dict, config: Config) -> set[date]:
    days = {date.fromisoformat(d) for ds in state.get("release_dates", {}).values() for d in ds}
    return days | set(config.extra_release_dates)


def check_due(state: dict, config: Config, now: datetime) -> Due:
    """Whether a run is due at `now` (timezone-aware, in the job's timezone)."""
    today, after_hour = now.date(), now.time() >= config.run_after
    last = state.get("last_good_run")
    if last is None:
        return Due(True, [], [], "first run")
    last_day = date.fromisoformat(last)
    pending = sorted(
        d for d in all_release_dates(state, config)
        if d > last_day and (d < today or (d == today and after_hour))
    )
    if not pending:
        return Due(False, [], [], "no release since the last good run")
    ran_on = {date.fromisoformat(r) for r in state.get("run_days", [])}
    missed = [d for d in pending if d < today and d not in ran_on]
    return Due(True, pending, missed, "release day" if pending[-1] == today else "catching up")


# -- one run ----------------------------------------------------------------

def run(config: Config, *, force: bool = False, dry_run: bool = False, now: datetime | None = None) -> dict:
    tz = ZoneInfo(config.timezone)
    now = now or datetime.now(tz)
    root = config.archive_dir
    archive = Archive(root)
    state = load_state(root)
    due = check_due(state, config, now)
    started = utc_now()

    if not (due.due or force):
        record = {"started": iso(started), "result": "not-due", "reason": due.reason}
        if not dry_run:
            with RunLock(root):
                visits = export_analytics(config, archive, state, now)
                save_state(root, state)
            record["analytics"] = visits
            if visits.get("stored"):
                record["backup"] = backup.sync(root)
            record["heartbeat"] = heartbeat.send(record)
            archive.append_run(record)
        return record

    released_through = now.date() if now.time() >= config.run_after else now.date() - timedelta(days=1)
    ctx = RunContext(archive=archive, http=HttpClient(config.user_agent, config.request_pause_seconds),
                     today=now.date(), released_through=released_through, dry_run=dry_run)
    if dry_run:
        _run_sources(ctx, state)
        return {"result": "dry-run", "due": due.reason, "planned": ctx.planned}

    with RunLock(root):
        archive.clean_tmp()
        _run_sources(ctx, state)
        visits = export_analytics(config, archive, state, now)
        good = not ctx.failures
        run_days = set(state.get("run_days", []))
        run_days.add(now.date().isoformat())
        state["run_days"] = sorted(run_days)[-400:]
        if good:
            state["last_good_run"] = released_through.isoformat()
        save_state(root, state)

    stored = [r for r in ctx.results if r.status == "stored"]
    unchanged = [r for r in ctx.results if r.status == "unchanged"]
    to_back_up = archive.stored_since(state.get("backup_mark"))
    report = render_report(config, now, due, force, stored, unchanged, ctx, to_back_up)
    flag = "ALERT: " if (ctx.failures or ctx.alerts) else ""
    subject = f"{flag}archive run {now.date().isoformat()}: {len(stored)} new, {len(ctx.failures)} failed"
    sent_to = notify(config, subject, report)
    record = {
        "started": iso(started), "finished": iso(utc_now()), "result": "ok" if good else "failures",
        "reason": "forced" if force and not due.due else due.reason,
        "release_days": [d.isoformat() for d in due.release_days],
        "missed": [d.isoformat() for d in due.missed],
        "stored": len(stored), "unchanged": len(unchanged), "failures": ctx.failures,
        "alerts": len(ctx.alerts), "report": sent_to, "analytics": visits,
    }
    if stored or visits.get("stored"):
        record["backup"] = backup.sync(root)
    record["heartbeat"] = heartbeat.send(record)
    archive.append_run(record)
    if config.release.enabled and good:
        from traceconomics import release   # imports this module; loaded only when needed

        if new_inputs := release.feeds_store(archive, stored):
            record["release"] = release.build(config, reason="new data: " + ", ".join(sorted(set(new_inputs))))["id"]
    return record


def export_analytics(config: Config, archive: Archive, state: dict, now: datetime) -> dict:
    """Copy the finished days of visit counts into the archive; alert if it falls behind.

    A failure doesn't fail the run (the sources are what the run is for), but Cloudflare keeps
    exact rows for only 7 days, so after ANALYTICS_ALERT_DAYS missing days an email goes out.
    """
    today = now.astimezone(UTC).date()
    if analytics.STATE_KEY not in state:
        # The state is a rebuildable cache: the latest finished day in the archive came last (a
        # manual export of one day may be stored after later ones, or be today's, not yet over).
        days = [d for s in archive.snapshots(analytics.SOURCE, analytics.DATASET)
                if (d := archive.manifest(s).get("day")) and date.fromisoformat(d) < today]
        if days:
            state[analytics.STATE_KEY] = max(days)
    result = analytics.export(archive, state, today)
    if result.get("result") == "failed":
        through = state.get(analytics.STATE_KEY)
        behind = (today - date.fromisoformat(through)).days - 1 if through else None
        if behind is None or behind >= ANALYTICS_ALERT_DAYS:
            missing = "no day copied yet" if behind is None else f"{behind} days not copied"
            result["alert"] = notify(
                config, f"ALERT: analytics export failing, {missing}",
                f"The visit-count export failed: {result.get('error')}\n\nCloudflare keeps exact rows for 7 days. "
                f"Last day copied: {through or 'none'}. Fix the cause (a 401 or 403 means the token expired or "
                "was revoked), then run `traceconomics analytics export`.\n")
    return result


def _run_sources(ctx: RunContext, state: dict) -> None:
    """ELSTAT first (nobody else keeps its files), then Eurostat, then the terms pages."""
    dates = state.setdefault("release_dates", {})
    for topic, days in elstat.run(ctx, state).items():
        if days:
            dates[f"elstat-{topic}"] = sorted({*dates.get(f"elstat-{topic}", []), *(d.isoformat() for d in days)})
    euro_dates = eurostat.run(ctx, state)
    if euro_dates:
        dates["eurostat-hicp"] = sorted({*dates.get("eurostat-hicp", []), *(d.isoformat() for d in euro_dates)})
    terms.run(ctx)


def render_report(config, now, due, force, stored, unchanged, ctx, to_back_up) -> str:
    lines = [f"Archive run at {now:%Y-%m-%d %H:%M} ({config.timezone}).",
             f"Why: {'forced by hand' if force and not due.due else due.reason}."]
    if due.release_days:
        lines.append("Release days covered: " + ", ".join(d.isoformat() for d in due.release_days))
    if due.missed:
        lines.append("MISSED (no run on the day): " + ", ".join(d.isoformat() for d in due.missed))
    for title, items in (("ALERTS", ctx.alerts), ("FAILURES", ctx.failures)):
        if items:
            lines += ["", f"{title}:"] + [f"- {x}" for x in items]
    lines += ["", f"New files stored: {len(stored)}. Checked and unchanged: {len(unchanged)}."]
    lines += [f"- {r.source}/{r.dataset}" for r in stored]
    lines += ["", f"Archive folder: {config.archive_dir}",
              f"Files to back up (stored since the last `traceconomics backup-done`): {len(to_back_up)}"]
    lines += [f"- {r['path']}" for r in to_back_up[:200]]
    if len(to_back_up) > 200:
        lines.append(f"- ... and {len(to_back_up) - 200} more (see `traceconomics status`)")
    return "\n".join(lines)


def fetch_history(config: Config, years: list[int], *, pause_seconds: float, dry_run: bool = False) -> dict:
    """One-off: archive past years of ELSTAT's CPI table 07, slowly, and report like a run."""
    root = config.archive_dir
    archive = Archive(root)
    started = utc_now()
    today = datetime.now(ZoneInfo(config.timezone)).date()
    ctx = RunContext(archive=archive, http=HttpClient(config.user_agent, pause_seconds),
                     today=today, released_through=today, dry_run=dry_run)
    if dry_run:
        elstat_history.fetch_years(ctx, years)
        return {"result": "dry-run", "planned": ctx.planned}

    with RunLock(root):
        archive.clean_tmp()
        notes = elstat_history.fetch_years(ctx, years)

    stored = [r for r in ctx.results if r.status == "stored"]
    to_back_up = archive.stored_since(load_state(root).get("backup_mark"))
    lines = [f"One-off fetch of past CPI table 07 files for {', '.join(map(str, years))}.", ""]
    for title, items in (("ALERTS", ctx.alerts), ("FAILURES", ctx.failures)):
        if items:
            lines += [f"{title}:"] + [f"- {x}" for x in items] + [""]
    lines += [f"- {n}" for n in notes]
    lines += ["", f"New files stored: {len(stored)}.", f"Archive folder: {config.archive_dir}",
              f"Files to back up (stored since the last `traceconomics backup-done`): {len(to_back_up)}"]
    lines += [f"- {r['path']}" for r in to_back_up[:200]]
    flag = "ALERT: " if (ctx.failures or ctx.alerts) else ""
    sent_to = notify(config, f"{flag}history fetch: {len(stored)} new, {len(ctx.failures)} failed", "\n".join(lines))
    record = {
        "started": iso(started), "finished": iso(utc_now()),
        "result": "ok" if not ctx.failures else "failures",
        "reason": "history fetch, CPI table 07 " + ",".join(map(str, years)),
        "stored": len(stored), "unchanged": len([r for r in ctx.results if r.status == "unchanged"]),
        "failures": ctx.failures, "alerts": len(ctx.alerts), "report": sent_to,
    }
    archive.append_run(record)
    return record


def mark_backup_done(config: Config) -> str:
    state = load_state(config.archive_dir)
    state["backup_mark"] = iso(utc_now())
    save_state(config.archive_dir, state)
    return state["backup_mark"]
