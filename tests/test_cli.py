"""The command line: what each command prints and the exit code it returns.

The work behind a command (a check, an export, an upload) has its own tests; here it is replaced by
a stand-in returning a known result, so the tests show what the command makes of that result: the
report a person reads and the exit code a scheduled run acts on. The tests that need no stand-in
run on a real archive in a temporary folder.
"""

import functools
import hashlib
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from clitools import no_store, run, setup  # noqa: F401 - fixtures

from traceconomics import __version__, analytics, backup, cli, config as config_mod, job, release, schedule
from traceconomics.archive.store import Archive

pytestmark = pytest.mark.unit

NOW = datetime(2026, 11, 1, tzinfo=UTC)


def _sha(b):
    return hashlib.sha256(b).hexdigest()


# -- the command line itself -------------------------------------------------------------------


def test_version_prints_the_package_version(capsys):
    """PY-CLI-001: --version prints the package version

    Given the command line
    When it is run with --version
    Then it exits with code 0
    And it prints the package's version
    """
    with pytest.raises(SystemExit) as exc:
        cli.main(["--version"])
    assert exc.value.code == 0
    assert capsys.readouterr().out.strip() == __version__


def test_a_missing_config_file_stops_with_a_usage_error(tmp_path, capsys):
    """PY-CLI-002: a missing config file stops the command with a usage error

    Given a config path where no file exists
    When the status command is run with it
    Then it exits with code 2
    And the error names the missing file and how to make one
    """
    missing = tmp_path / "nowhere.toml"
    with pytest.raises(SystemExit) as exc:
        cli.main(["--config", str(missing), "status"])
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert f"No config file at {missing}" in err and "config.example.toml" in err


def test_the_config_given_is_passed_on_to_later_steps(setup, monkeypatch):
    """PY-CLI-003: the config file given on the command line is passed on to the steps a run starts

    Given a config file passed with --config
    When a command is run with it
    Then TRACECONOMICS_CONFIG holds the file's absolute path afterwards

    A release runs its steps as separate processes; they must read the same file.
    """
    import os

    monkeypatch.chdir(setup.path.parent)
    assert cli.main(["--config", setup.path.name, "backup-done"]) == 0
    assert os.environ[config_mod.CONFIG_ENV] == str(setup.path.resolve())


def test_a_run_that_finds_the_lock_taken_is_skipped(setup, run):
    """PY-CLI-004: a run that finds another run's lock is skipped, not failed

    Given another run holding the store's lock
    When the store update command is run
    Then it exits with code 0
    And it prints that the run was skipped
    """
    with job.RunLock(setup.cfg.store_dir):
        code, out = run("store", "update")
    assert code == 0 and out.startswith("Skipped:")


def test_a_crash_is_reported_and_fails_the_run(setup, run, monkeypatch):
    """PY-CLI-005: a crash is reported through the alert channel and fails the run

    Given a configuration without email settings
    And a status command whose work raises an unexpected error
    When it is run
    Then it exits with code 1
    And it prints the traceback and where the crash report went
    And the report in the outbox is titled "ALERT: traceconomics status crashed" and holds the error

    A scheduled run has no console, so a crash must reach the owner some other way.
    """

    def broken(*a, **k):
        raise RuntimeError("disk on fire")

    monkeypatch.setattr(job, "load_state", broken)
    code, out = run("status")
    assert code == 1
    assert "RuntimeError: disk on fire" in out and "Crash report sent to: " in out
    report = Path(out.split("Crash report sent to: ")[1].strip())
    text = report.read_text(encoding="utf-8")
    assert "ALERT: traceconomics status crashed" in text and "disk on fire" in text


def test_migrate_local_runs_without_a_config_and_reports_problems(tmp_path, capsys, monkeypatch):
    """PY-CLI-006: migrate-local runs before any config exists and fails on a problem

    Given no config file anywhere
    And a migration that has one step and one problem
    When migrate-local is run as a dry run
    And it is run for real with no problems left
    Then the dry run prints the step as "would ..." and the problem as "PROBLEM ...", and exits with code 1
    And the real run prints the step as done and exits with code 0

    The config under the project's new name may not exist yet: that is what the command creates.
    """
    from traceconomics import migrate

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "empty"))
    monkeypatch.delenv(config_mod.CONFIG_ENV, raising=False)
    plans = iter(
        [
            SimpleNamespace(steps=["move a to b"], problems=["c is in the way"]),
            SimpleNamespace(steps=["move a to b"], problems=[]),
        ]
    )
    calls = []
    monkeypatch.setattr(migrate, "run", lambda dry_run: calls.append(dry_run) or next(plans))
    assert cli.main(["migrate-local", "--dry-run"]) == 1
    assert capsys.readouterr().out.splitlines() == ["would move a to b", "PROBLEM c is in the way"]
    assert cli.main(["migrate-local"]) == 0
    assert capsys.readouterr().out.splitlines() == ["move a to b"]
    assert calls == [True, False]


# -- the archive job and one-off fetches -----------------------------------------------------------


@pytest.mark.parametrize("result, code", [("ok", 0), ("not-due", 0), ("dry-run", 0), ("partial", 1)])
def test_archive_prints_the_run_and_fails_unless_it_went_well(run, monkeypatch, result, code):
    """PY-CLI-007: archive prints the job's result and fails unless the run went well

    Given an archive job that ends with a given result
    When the archive command is run with --force
    Then it prints the result as JSON
    And the job was asked to run even though nothing is due
    And it exits with code 0 for ok, not-due and dry-run, and 1 otherwise
    """
    seen = {}
    monkeypatch.setattr(
        job,
        "run",
        lambda cfg, force, dry_run: seen.update(force=force, dry_run=dry_run) or {"result": result, "stored": 2},
    )
    got, out = run("archive", "--force")
    assert json.loads(out) == {"result": result, "stored": 2}
    assert seen == {"force": True, "dry_run": False}
    assert got == code


@pytest.mark.parametrize("result, code", [("ok", 0), ("dry-run", 0), ("failed", 1)])
def test_fetch_history_passes_the_years_and_pause(run, monkeypatch, result, code):
    """PY-CLI-008: fetch-history reads the years and the pause, and fails unless the fetch went well

    Given a history fetch that ends with a given result
    When fetch-history cpi07 is run for "2011-2013,2015" with a 5 second pause as a dry run
    Then the fetch is asked for 2011, 2012, 2013 and 2015, with the pause and the dry run
    And it prints the result as JSON
    And it exits with code 0 for ok and dry-run, and 1 otherwise
    """
    seen = {}

    def fetch(cfg, years, pause_seconds, dry_run):
        seen.update(years=years, pause=pause_seconds, dry_run=dry_run)
        return {"result": result}

    monkeypatch.setattr(job, "fetch_history", fetch)
    got, out = run("fetch-history", "cpi07", "--years", "2011-2013,2015", "--pause", "5", "--dry-run")
    assert seen == {"years": [2011, 2012, 2013, 2015], "pause": 5.0, "dry_run": True}
    assert json.loads(out) == {"result": result} and got == code


@pytest.mark.integration
def test_import_stores_a_file_downloaded_by_hand(setup, run, tmp_path):
    """PY-CLI-009: import stores a file downloaded by hand, once

    Given a file "hbs-2025.zip" downloaded by hand on 2026-01-02
    When it is imported with that date
    And it is imported again
    Then the first import prints "stored: elstat/puf-hbs-2025" and the archived path, and exits with code 0
    And the archived snapshot is dated 2026-01-02
    And the second import prints "unchanged" without a path
    """
    f = tmp_path / "hbs-2025.zip"
    f.write_bytes(b"microdata stand-in")
    code, out = run("import", str(f), "--downloaded", "2026-01-02")
    assert code == 0 and out.startswith("stored: elstat/puf-hbs-2025 -> ")
    assert Archive(setup.cfg.archive_dir).latest("elstat", "puf-hbs-2025")["retrieved_at"].startswith("2026-01-02")
    code, out = run("import", str(f))
    assert code == 0 and out.strip() == "unchanged: elstat/puf-hbs-2025"


@pytest.mark.integration
def test_seed_reports_each_file_and_fails_on_a_bad_checksum(setup, run, tmp_path):
    """PY-CLI-010: seed reports what it stored, and fails on a bad checksum

    Given a research folder whose manifest lists one matching file and one changed file
    When seed is run
    Then it prints "stored: 1" and lists the stored file with "+"
    And it lists the changed file as "BAD CHECKSUM"
    And it exits with code 1
    And the matching file is in the archive
    """
    _research(tmp_path, bad=True)
    code, out = run("seed", str(tmp_path / "research"))
    assert code == 1 and out.startswith("stored: 1;")
    assert "  + elstat/doc-1" in out and "  ! BAD CHECKSUM" in out
    assert Archive(setup.cfg.archive_dir).latest("elstat", "doc-1") is not None


@pytest.mark.integration
def test_seed_dry_run_lists_without_storing(setup, run, tmp_path):
    """PY-CLI-037: seed as a dry run lists what it would store and stores nothing

    Given a research folder whose manifest lists one matching file
    When seed is run as a dry run
    Then it prints "would store: 1" and lists the file with "+"
    And it exits with code 0
    And nothing is in the archive
    """
    _research(tmp_path, bad=False)
    code, out = run("seed", str(tmp_path / "research"), "--dry-run")
    assert code == 0 and out.startswith("would store: 1;") and "  + elstat/doc-1" in out
    assert Archive(setup.cfg.archive_dir).latest("elstat", "doc-1") is None


def _research(tmp_path, *, bad):
    folder = tmp_path / "research" / "pass-2026-10-17"
    folder.mkdir(parents=True)
    doc = "https://www.statistics.gr/en/statistics?_documentID={}&_locale=en"
    (folder / "good.xlsx").write_bytes(b"good")
    rows = f"| good.xlsx | {doc.format(1)} | 2026-10-17 | {_sha(b'good')} | ok |\n"
    if bad:
        (folder / "bad.xlsx").write_bytes(b"tampered")
        rows += f"| bad.xlsx | {doc.format(2)} | 2026-10-17 | {_sha(b'original')} | changed |\n"
    (folder / "MANIFEST.md").write_text(
        "| File | Source URL | Downloaded | SHA-256 | What |\n|---|---|---|---|---|\n" + rows, encoding="utf-8"
    )


# -- status, backup marks, alerts ------------------------------------------------------------------


@pytest.mark.integration
def test_status_shows_runs_release_days_and_files_waiting_for_backup(setup, run):
    """PY-CLI-011: status shows the last runs, the next release days and the files waiting for backup

    Given an archive with one stored file, one recorded run, a last good run and a release day tomorrow
    When status is run
    And backup-done is run, then status again
    Then the first status names the archive, the last good run, tomorrow as the next release day and the run
    And it counts 1 file waiting for backup since the start
    And backup-done prints the time it recorded
    And after backup-done status counts 0 files waiting, since that time
    """
    Archive(setup.cfg.archive_dir).store_bytes("eurostat", "prc_hicp_iw", b"x", url=None, retrieved_at=NOW, ext=".tsv")
    Archive(setup.cfg.archive_dir).append_run(
        {"started": "2026-11-01T12:00:00Z", "result": "ok", "reason": "due", "stored": 1}
    )
    tomorrow = date.today() + timedelta(days=1)
    job.save_state(
        setup.cfg.archive_dir,
        {"last_good_run": "2026-11-01", "release_dates": {"elstat": [tomorrow.isoformat(), "2000-01-01"]}},
    )
    code, out = run("status")
    assert code == 0
    assert f"Archive: {setup.cfg.archive_dir}" in out
    assert "Last good run (releases covered through): 2026-11-01" in out
    assert f"Next release days: {tomorrow.isoformat()}" in out
    assert "run 2026-11-01T12:00:00Z: ok (due) stored=1 failures=0" in out
    assert "Files waiting for backup since the start: 1" in out
    code, out = run("backup-done")
    assert code == 0
    mark = out.split("Backup recorded at ")[1].split(" (UTC)")[0]
    code, out = run("status")
    assert f"Files waiting for backup since {mark}: 0" in out


def test_status_says_when_nothing_is_known(run):
    """PY-CLI-012: status on a new archive says what isn't known yet

    Given an empty archive with no saved state
    When status is run
    Then it says the last good run was never
    And that no release day is known
    """
    code, out = run("status")
    assert code == 0
    assert "Last good run (releases covered through): never" in out and "Next release days: none known" in out


def test_notify_test_writes_a_test_message(run):
    """PY-CLI-013: notify-test sends a test message through the configured channel

    Given a configuration without email settings
    When notify-test is run
    Then it exits with code 0
    And it prints where the message went
    And that file is a test message
    """
    code, out = run("notify-test")
    assert code == 0
    where = Path(out.removeprefix("Sent to: ").strip())
    assert "Subject: [Traceconomics] test message" in where.read_text(encoding="utf-8")


# -- backups, analytics, releases --------------------------------------------------------------------


def test_backup_plan_lists_at_most_fifty_files(run, monkeypatch):
    """PY-CLI-014: backup plan counts every file to send and lists the first fifty

    Given 60 archive files not yet backed up
    When backup plan is run
    Then it prints "60 files to send"
    And it lists the first 50 by name, not the rest
    """
    monkeypatch.setattr(backup, "plan", lambda root: [(f"f{n:02d}", None) for n in range(60)])
    code, out = run("backup", "plan")
    lines = out.splitlines()
    assert code == 0 and lines[0] == "60 files to send"
    assert lines[1:] == [f"  f{n:02d}" for n in range(50)]


@pytest.mark.parametrize("result, code", [("ok", 0), ("off", 0), ("failed", 1)])
def test_backup_sync_fails_unless_it_sent_or_is_off(run, monkeypatch, result, code):
    """PY-CLI-015: backup sync prints its result and fails unless it sent the files or is switched off

    Given a backup upload that ends with a given result
    When backup sync is run
    Then it prints the result as JSON
    And it exits with code 0 for ok and off, and 1 otherwise
    """
    monkeypatch.setattr(backup, "sync", lambda root: {"result": result, "sent": 3})
    got, out = run("backup", "sync")
    assert json.loads(out) == {"result": result, "sent": 3} and got == code


def test_analytics_for_one_day_runs_each_feed_and_reports_a_failure(run, monkeypatch):
    """PY-CLI-016: analytics export for one day runs each feed and reports a feed's failure

    Given a visits feed that copies its day and a downloads feed whose request fails
    When analytics export is run for --day 2026-11-01
    Then each feed is asked for 2026-11-01
    And it prints both results as JSON, the failed one with its error
    And it exits with code 1
    """
    asked = []

    def export_day(archive, day, feed):
        asked.append((feed.name, day))
        if feed.name == "downloads":
            raise analytics.AnalyticsError("no zone id")
        return {"result": "ok"}

    monkeypatch.setattr(analytics, "export_day", export_day)
    code, out = run("analytics", "export", "--day", "2026-11-01")
    assert asked == [("visits", date(2026, 11, 1)), ("downloads", date(2026, 11, 1))]
    assert json.loads(out) == {"visits": {"result": "ok"}, "downloads": {"result": "failed", "error": "no zone id"}}
    assert code == 1


def test_analytics_without_a_day_follows_the_bookmark_and_saves_it(setup, run, monkeypatch):
    """PY-CLI-017: analytics export without a day copies from the bookmark and saves the moved bookmark

    Given a visits feed whose export moves its bookmark
    When analytics export is run for the visits feed only
    Then only the visits feed runs
    And the moved bookmark is saved in the job's state
    And it prints the result and exits with code 0
    """

    def export(cfg, archive, state, now, feed):
        state["analytics_through"] = "2026-11-01"
        return {"result": "ok", "feed": feed.name}

    monkeypatch.setattr(job, "export_analytics", export)
    code, out = run("analytics", "export", "--feed", "visits")
    assert json.loads(out) == {"visits": {"result": "ok", "feed": "visits"}} and code == 0
    assert job.load_state(setup.cfg.archive_dir)["analytics_through"] == "2026-11-01"


def _record(result):
    rec = {
        "id": "20261107T120000Z",
        "reason": "manual",
        "result": result,
        "steps": [{"name": "series", "code": 0 if result == "ok" else 1, "seconds": 3}],
    }
    if result == "ok":
        rec |= {
            "preview_url": "https://preview.example",
            "changes": {"first_release": True, "latest_period": "2026-10"},
        }
    else:
        rec |= {"failed_step": "series", "log_tail": ["boom"]}
    return rec


@pytest.mark.parametrize("result, code", [("ok", 0), ("failed", 1)])
def test_release_build_prints_its_report(setup, run, monkeypatch, result, code):
    """PY-CLI-018: release build prints the build's report and fails if the build failed

    Given a release build that ends with a given result
    When release build is run
    Then the build is given the config file the command read
    And it prints the build's report
    And it exits with code 0 if the build passed, 1 otherwise
    """
    seen = []
    monkeypatch.setattr(release, "build", lambda cfg, path: seen.append(path) or _record(result))
    got, out = run("release", "build")
    assert seen == [setup.path]
    assert out.startswith(f"Release 20261107T120000Z (manual): {result.upper()}") and got == code


@pytest.mark.parametrize(
    "args, message",
    [
        (["promote"], "Which build?"),
        (["retest"], "Which build?"),
        (["promote", "20261107T120000Z"], "Where to? Pass --to staging or --to production."),
    ],
)
def test_release_promote_and_retest_need_a_build_and_a_target(run, monkeypatch, args, message):
    """PY-CLI-019: release promote and retest refuse to guess the build or the target

    Given no build is named, or a promote names no target
    When release promote or retest is run
    Then it says what is missing
    And it exits with code 2
    And nothing is promoted or tested

    A promote changes what the public sees, so it never has a default.
    """

    def never(*a, **k):
        raise AssertionError("must not run")

    monkeypatch.setattr(release, "promote", never)
    monkeypatch.setattr(release, "retest", never)
    code, out = run("release", *args)
    assert code == 2 and message in out


def test_release_promote_retest_and_status(setup, run, monkeypatch):
    """PY-CLI-020: release promote, retest and status print what they did

    Given a build that promotes and retests cleanly, and two builds on disk
    When release promote is run with --to staging
    And release retest is run
    And release status is run
    Then the promote prints the build, the target, the address that serves it and when it was checked
    And the retest prints the build's report and exits with code 0
    And status lists each build with its result and where it is live
    """
    monkeypatch.setattr(
        release,
        "promote",
        lambda cfg, id, to: {"id": id, "to": to, "url": "https://staging.example", "confirmed": "2026-11-07T12:00:00Z"},
    )
    monkeypatch.setattr(release, "retest", lambda cfg, id, path: _record("ok"))
    monkeypatch.setattr(
        release,
        "status",
        lambda root: [
            {"id": "b2", "result": "ok", "on": ["staging", "production"], "preview_url": "https://p2"},
            {"id": "b1", "result": "failed", "on": [], "failed_step": "ui-test"},
        ],
    )
    code, out = run("release", "promote", "b2", "--to", "staging")
    assert code == 0
    assert out.strip() == "Promoted b2 to staging: https://staging.example serves it (checked 2026-11-07T12:00:00Z)"
    code, out = run("release", "retest", "b2")
    assert code == 0 and out.startswith("Release 20261107T120000Z (manual): OK")
    code, out = run("release", "status")
    lines = out.splitlines()
    assert lines[0].split() == ["b2", "ok", "staging,production", "https://p2"]
    assert lines[1].split() == ["b1", "failed", "ui-test"]


# -- schedule ----------------------------------------------------------------------------------------


def test_schedule_units_needs_a_folder_and_writes_the_units_there(run, tmp_path):
    """PY-CLI-021: schedule units needs a folder, then writes the units and the shell command there

    Given a Linux machine
    When schedule units is run without --out
    And it is run with --out and --bin folders
    Then the first run says where to point it and exits with code 2
    And the second writes the archive timer and service into --out and the traceconomics command into --bin
    And it prints each file written
    """
    code, out = run("schedule", "units")
    assert code == 2 and "Pass --out" in out
    units, bin_dir = tmp_path / "units", tmp_path / "bin"
    code, out = run("schedule", "units", "--out", str(units), "--bin", str(bin_dir))
    assert code == 0
    assert (units / "traceconomics-archive.timer").is_file() and (units / "traceconomics-archive.service").is_file()
    assert (bin_dir / "traceconomics").is_file()
    assert f"Wrote {bin_dir / 'traceconomics'}" in out


def test_schedule_install_remove_and_show_on_windows(run, monkeypatch):
    """PY-CLI-022: schedule install, remove and show report on the Windows task

    Given a Windows task scheduler that installs, removes and shows the task
    When schedule install, remove and show are run
    Then install prints the task's name and its daily time, 13:00
    And remove prints "Removed."
    And show prints what the task scheduler said
    """
    monkeypatch.setattr(schedule, "install", lambda cfg: "traceconomics-archive")
    monkeypatch.setattr(schedule, "remove", lambda: None)
    monkeypatch.setattr(schedule, "show", lambda: "TaskName: traceconomics-archive")
    assert run("schedule", "install")[1].startswith("Installed task traceconomics-archive: daily at 13:00")
    assert run("schedule", "remove")[1].strip() == "Removed."
    assert run("schedule", "show")[1].strip() == "TaskName: traceconomics-archive"


def test_schedule_install_on_linux_points_to_the_units(run):
    """PY-CLI-023: schedule install on Linux stops and points to the systemd units

    Given a Linux machine
    When schedule install is run
    Then the command stops with a message naming "schedule units"
    """
    with pytest.raises(SystemExit) as exc:
        run("schedule", "install")
    assert "schedule units" in str(exc.value.code)


# -- the store and the checks ------------------------------------------------------------------------


def test_store_refuses_an_unknown_dataset(run):
    """PY-CLI-024: store refuses a dataset it doesn't know

    Given a dataset name that isn't in the catalog
    When store update is run for it
    Then it names the unknown dataset and lists the known ones
    And it exits with code 2
    """
    code, out = run("store", "update", "--dataset", "eurostat:nope")
    assert code == 2
    assert "Unknown dataset(s): ['eurostat:nope']" in out and "eurostat:prc_hicp_iw" in out


@pytest.mark.integration
def test_store_update_reads_an_archived_dataset(setup, run, fixture_bytes):
    """PY-CLI-025: store update reads the chosen dataset's archived snapshot into the store

    Given an archive holding one snapshot of Eurostat's HICP monthly indices
    When store update is run for eurostat:prc_hicp_minr
    Then it exits with code 0
    And its report line names the dataset with one snapshot read
    And it prints the store's folder
    """
    Archive(setup.cfg.archive_dir).store_bytes(
        "eurostat",
        "prc_hicp_minr",
        fixture_bytes("eurostat_prc_hicp_minr.tsv.gz"),
        url=None,
        retrieved_at=NOW,
        ext=".tsv.gz",
    )
    code, out = run("store", "update", "--dataset", "eurostat:prc_hicp_minr")
    assert code == 0, out
    assert any("eurostat:prc_hicp_minr" in line and "1 snapshot" in line for line in out.splitlines()), out
    assert f"Store: {setup.cfg.store_dir}" in out


def test_check_v1_needs_the_archived_files(run):
    """PY-CLI-026: check v1 says which file to archive first

    Given an empty archive
    When check v1 is run
    Then it names eurostat/prc_hicp_minr as missing and says to run the archive job
    And it exits with code 1
    """
    code, out = run("check", "v1")
    assert code == 1 and "No archived eurostat/prc_hicp_minr; run `traceconomics archive` first." in out


@pytest.mark.integration
def test_check_v1_rebuilds_the_archived_hicp(setup, run, fixture_bytes):
    """PY-CLI-027: check v1 rebuilds Greece's HICP from the archived Eurostat files

    Given an archive holding the committed Greek extracts of the HICP indices and item weights
    When check v1 is run for GR
    And it is run for CY
    Then it names both archived files
    And it prints the finest-detail result
    And it ends with "V1 passed." and exit code 0
    And after the run for CY, a country the extract lacks, it says there is no all-items index for CY, with exit code 1
    """
    Archive(setup.cfg.archive_dir).store_bytes(
        "eurostat",
        "prc_hicp_minr",
        fixture_bytes("eurostat_v1_gr_minr.tsv.gz"),
        url=None,
        retrieved_at=NOW,
        ext=".tsv.gz",
    )
    Archive(setup.cfg.archive_dir).store_bytes(
        "eurostat", "prc_hicp_iw", fixture_bytes("eurostat_v1_gr_iw.tsv.gz"), url=None, retrieved_at=NOW, ext=".tsv.gz"
    )
    code, out = run("check", "v1", "--geo", "GR")
    assert out.count("Using ") == 2 and "finest detail" in out
    assert (code, out.strip().splitlines()[-1]) == (0, "V1 passed.")
    code, out = run("check", "v1", "--geo", "CY")
    assert code == 1 and "No all-items index for CY." in out


@pytest.mark.parametrize("passed", [True, False])
def test_check_v1_cpi_reports_missing_years_and_the_earlier_period(run, monkeypatch, passed):
    """PY-CLI-028: check v1-cpi reports missing years, the strict check and the earlier report-only years

    Given archived table 07 files for 2011, 2012 and 2014, and a strict check that passes or fails
    When check v1-cpi is run
    Then it prints the years covered and 2013 as missing
    And the earlier years' failures are shown as "outside the check", not as failures
    And it ends with "V1-CPI passed." and exit code 0, or "V1-CPI FAILED." and 1
    """
    from traceconomics.validate import v1_cpi

    checked = SimpleNamespace(passed=passed, summary=lambda: "strict from 2014")
    earlier = SimpleNamespace(summary=lambda: "fixed basket, FAIL")
    monkeypatch.setattr(v1_cpi, "run_archive", lambda archive: (checked, earlier, 0, {2011: "a", 2012: "b", 2014: "c"}))
    code, out = run("check", "v1-cpi")
    assert "Table 07 files for 2011-2014 (3 years)" in out and "Missing years: [2013]" in out
    assert "fixed basket, outside the check" in out and "FAIL" not in out.replace("FAILED", "")
    assert (code, out.strip().splitlines()[-1]) == ((0, "V1-CPI passed.") if passed else (1, "V1-CPI FAILED."))


def test_check_v3_flags_years_that_need_an_explanation(run, monkeypatch, no_store):
    """PY-CLI-029: check v3 prints each year and flags a large weights effect that has no explanation

    Given V3 rows for a year with a small weights effect and a year with a large unexplained one
    When check v3 is run
    Then both spending concepts are printed
    And only the year with the large effect is flagged "TO EXPLAIN"
    And it exits with code 0 (V3 is a report)
    """
    from traceconomics.module1 import checks

    rows = [
        SimpleNamespace(year=1990, official=2.0, l1=2.1, l2=2.2, weights_effect=0.1, timing_effect=0.1),
        SimpleNamespace(
            year=1991, official=2.0, l1=4.0, l2=4.2, weights_effect=checks.REPORT_PP + 1, timing_effect=0.2
        ),
    ]
    monkeypatch.setattr(checks, "v3", lambda con, archive, spending: rows)
    code, out = run("check", "v3")
    assert code == 0 and "purchases:" in out and "all:" in out
    flagged = [line for line in out.splitlines() if "<-" in line]
    assert len(flagged) == 2 and all("1991" in line and "TO EXPLAIN" in line for line in flagged)


@pytest.mark.parametrize("ours, official, code", [(0.124, 0.12, 0), (0.104, 0.12, 1)])
def test_check_v6_passes_within_rounding_only(run, monkeypatch, no_store, ours, official, code):
    """PY-CLI-030: check v6 passes when the largest difference is within rounding

    Given a V6 result whose worst contribution, rounded to two decimals, is 0.00 or 0.02 pp off Eurostat's
    When check v6 is run
    Then it prints how many contributions are equal and the largest difference
    And it passes with exit code 0 within 0.01 pp, and fails with 1 beyond it
    """
    from traceconomics.module1 import checks

    monkeypatch.setattr(
        checks,
        "v6",
        lambda con, archive: SimpleNamespace(worst=("2022-10", "CP01", ours, official), exact=10, compared=12),
    )
    got, out = run("check", "v6")
    assert "10/12 equal" in out and "2022-10, division CP01" in out
    assert got == code and out.strip().endswith("V6 passed." if code == 0 else "V6 FAILED (more than rounding).")


def test_check_v4_fails_on_bruegel_and_reports_kepe(run, monkeypatch, no_store):
    """PY-CLI-031: check v4 fails on a Bruegel gap and reports KEPE without a verdict

    Given a Bruegel rebuild that fails, with one provisional year, and a KEPE rebuild
    When check v4 is run
    Then it prints Bruegel's result with its largest monthly gap and annual averages
    And it names the provisional year as not compared
    And it prints KEPE's annual averages against the published chart
    And it exits with code 1, Bruegel being the tier-B check
    """
    from traceconomics.module1 import benchmarks

    monkeypatch.setattr(
        benchmarks,
        "v4_bruegel",
        lambda con, archive: [
            SimpleNamespace(
                name="Bruegel EL",
                passed=False,
                months=36,
                worst_month=("2022-06", 10.0, 9.5),
                annual={2022: (9.0, 8.8)},
                provisional=["2023"],
            )
        ],
    )
    pub = {k: {"2022": 9.9} for k in ("P20", "R20", "R10")}
    monkeypatch.setattr(benchmarks, "kepe_published", lambda: {"chart1": pub})
    rates = {k: {2022: 9.5} for k in ("P20", "R20", "R10")}
    monkeypatch.setattr(
        benchmarks, "v4_kepe", lambda con: {("purchases", "income"): {"rates": rates, "max_gap": 0.4, "mean_gap": 0.4}}
    )
    code, out = run("check", "v4")
    assert "Bruegel EL: FAIL; 36 months, largest gap 0.50 pp (2022-06); annual averages 2022 9.00/8.80" in out
    assert "provisional data: 2023" in out
    assert "purchases, ranking income: largest gap 0.40, mean 0.40" in out and "P20 2022:9.50/9.9" in out
    assert code == 1 and out.strip().endswith("V4 FAILED (Bruegel, tier B).")


def test_check_v5_prints_each_setting_gap(run, monkeypatch, no_store):
    """PY-CLI-032: check v5 prints each setting's gap for Bruegel and KEPE

    Given attribution rows for Bruegel and KEPE over two years
    When check v5 is run
    Then it prints a header with the years and one line per setting with signed gaps
    And it exits with code 0 (V5 is a report)
    """
    from traceconomics.module1 import attribution

    monkeypatch.setattr(attribution, "v5_bruegel", lambda con, archive: {"their settings": {2021: 0.5, 2022: -1.25}})
    monkeypatch.setattr(attribution, "v5_kepe", lambda con, archive: {"our default": {2021: 0.0, 2022: 2.0}})
    code, out = run("check", "v5")
    assert code == 0
    assert any(line.startswith("Bruegel (Q1-Q5)") and "2021" in line and "2022" in line for line in out.splitlines())
    assert any(line.startswith("their settings") and "+0.50" in line and "-1.25" in line for line in out.splitlines())
    assert any(line.startswith("our default") and "+2.00" in line for line in out.splitlines())


@pytest.mark.parametrize("ok", [True, False])
def test_check_combos_prints_the_identities_and_the_option_effects(run, monkeypatch, tmp_path, ok):
    """PY-CLI-033: check combos prints the identities and each option's effect, and fails on a broken identity

    Given module 1 outputs whose identities hold, or break once
    And an earlier build to compare the default with
    When check combos is run with both folders
    Then the identity check is given both outputs' m1 folders
    And it prints each identity, the price source, timing, imputed rent and tutoring tables
    And it ends with "Identities passed." and exit code 0, or "Identities FAILED." and 1
    """
    from traceconomics.module1 import combos_check as cc

    seen = []
    monkeypatch.setattr(
        cc,
        "identities",
        lambda folder, base: (
            seen.append((folder, base))
            or [
                ("weights sum to 1", True, "48 settings"),
                ("rates match the index", ok, "2 rows off" if not ok else "all"),
            ]
        ),
    )
    monkeypatch.setattr(
        cc,
        "source",
        lambda folder: {
            2022: {"all_cpi": 9.3, "all_hicp": 9.4, "gap_cpi": 1.0, "gap_hicp": 1.2},
            2023: {"all_cpi": 3.5, "all_hicp": 4.2, "gap_cpi": None, "gap_hicp": None},
        },
    )
    monkeypatch.setattr(cc, "timing", lambda folder: {2022: {"N": 1.0, "F": None, "U": 0.5}})
    monkeypatch.setattr(cc, "rent", lambda folder: {"Q1": {"weight_2025": 0.12, "change": {2010: 0.1, 2011: 0.2}}})
    monkeypatch.setattr(
        cc,
        "tutoring",
        lambda folder: {
            "period": "2026-01",
            "groups": {
                "all": {
                    "priced": 2.5,
                    "excluded": 2.25,
                    "education_weight_priced": 0.03,
                    "education_weight_excluded": 0.02,
                }
            },
        },
    )
    outputs, earlier = tmp_path / "out", tmp_path / "earlier"
    code, out = run("check", "combos", "--outputs", str(outputs), "--baseline", str(earlier))
    assert seen == [(outputs / "gr" / "m1", earlier / "gr" / "m1")]
    assert "ok   weights sum to 1: 48 settings" in out
    assert ("ok   rates match the index" if ok else "FAIL rates match the index: 2 rows off") in out
    assert "2022    9.30   9.40  (+0.10)   gap +1.0 +1.2" in out
    assert "N +1.0  F   -   U +0.5" in out
    assert "weight 0.120   2010 +0.10" in out and "2011" not in out.split("weight 0.120")[1].splitlines()[0]
    assert "  2.50   2.25  (-0.25)   0.0300 0.0200" in out
    assert (code, out.strip().splitlines()[-1]) == ((0, "Identities passed.") if ok else (1, "Identities FAILED."))


def test_check_seam_and_prices_are_reports(run, monkeypatch, no_store):
    """PY-CLI-034: check seam and check prices print their reports

    Given a seam result for one group and a price comparison for one year
    When check seam and check prices are run
    Then seam prints the group's original and re-issued 2010 movement and their difference
    And prices prints the year's pairs, median gap, share within 0.1 pp and largest gap
    And both exit with code 0
    """
    from traceconomics.module1 import checks

    monkeypatch.setattr(checks, "seam", lambda con, archive: {"all households": (4.75, 4.5)})
    monkeypatch.setattr(
        checks, "v_prices", lambda con: {2020: {"pairs": 120, "median": 0.012, "within_0.1": 0.9, "max": 3.5}}
    )
    code, out = run("check", "seam")
    assert code == 0 and "original   4.75%   re-issued   4.50%   difference +0.25 pp" in out
    code, out = run("check", "prices")
    assert code == 0 and "2020     120      0.012          90%       3.50" in out


# -- exports and module 1 ----------------------------------------------------------------------------


def test_export_skeleton_and_site(run, monkeypatch, no_store, tmp_path):
    """PY-CLI-035: export writes the skeleton or the site's data and lists what it wrote

    Given a skeleton export that writes one file and a site export that writes three
    When export skeleton is run
    And export site is run with --no-downloads
    Then the skeleton export prints the file it wrote
    And the site export is told to skip the download files and to read the given outputs folder
    And it prints how many files it wrote and where
    """
    from traceconomics.export import site, skeleton

    out_dir, outputs = tmp_path / "data", tmp_path / "outputs"
    monkeypatch.setattr(skeleton, "export", lambda con, out: [out / "hicp.json"])
    seen = {}

    def site_export(con, archive, outputs_dir, out, with_downloads, log):
        seen.update(outputs=outputs_dir, downloads=with_downloads)
        log("working")
        return ["a", "b", "c"]

    monkeypatch.setattr(site, "export", site_export)
    code, out = run("export", "skeleton", "--out", str(out_dir))
    assert code == 0 and out.strip() == f"Wrote {out_dir / 'hicp.json'}"
    code, out = run("export", "site", "--out", str(out_dir), "--outputs", str(outputs), "--no-downloads")
    assert seen == {"outputs": outputs, "downloads": False}
    assert code == 0 and out.splitlines() == ["working", f"Wrote 3 files under {out_dir / site.FORMAT}"]


@pytest.mark.integration
def test_module1_run_writes_the_default_setting(setup, run, monkeypatch, tmp_path):
    """PY-CLI-036: module1 run computes the chosen settings and writes their files

    Given the made-up store and prices of the site's browser tests
    When module1 run is run for the default setting, purchases only
    Then it prints one progress line for the one setting, naming its series and their months
    And it writes the index, rates, availability and metadata files under gr/m1
    And it ends with the writer's row counts as JSON
    And it exits with code 0
    """
    import sitedata

    from traceconomics.module1 import combinations, index

    cpi, hicp = sitedata.blocks(), sitedata.blocks(hicp=True)
    sitedata.write_store(setup.cfg.store_dir, cpi, hicp)
    real = combinations.iterate
    monkeypatch.setattr(
        combinations, "iterate", functools.partial(real, blocks={"cpi": cpi, "hicp": hicp}, baskets=sitedata.baskets())
    )
    monkeypatch.setattr(index, "build_all", lambda con, archive, spending, groups: [])
    monkeypatch.setattr(index, "price_blocks", lambda con, archive: cpi)
    out_dir = tmp_path / "outputs"
    code, out = run("module1", "run", "--out", str(out_dir), "--combinations", "default", "--spending", "purchases")
    assert code == 0
    progress = [line for line in out.splitlines() if line.startswith("[")]
    assert len(progress) == 1 and progress[0].startswith("[1/1] ") and " series, " in progress[0]
    folder = out_dir / "gr" / "m1"
    assert (folder / "availability.json").is_file() and (folder / "metadata.json").is_file()
    assert any(p.name.startswith("m1_index") for p in folder.rglob("*.parquet"))
    assert isinstance(json.loads(out.strip().splitlines()[-1]), dict)


@pytest.mark.integration
def test_module5_run_prints_each_check_and_writes_its_files(setup, run, monkeypatch, tmp_path):
    """PY-CLI-044: module5 run prints each check's count and writes the results

    Given the made-up store of the site's browser tests, and one check of three months with one difference to rounding
    And no survey tables or questions in the store
    When module5 run is run
    Then it prints the check's count, its span and its differences by cause
    And it says the survey tables and income limits aren't in the store yet
    And it writes the check's CSV and checks.json under gr/m5, and exits with code 0
    """
    import sitedata

    from traceconomics.module5 import run as m5
    from traceconomics.module5.record import Check, Comparison

    sitedata.write_store(setup.cfg.store_dir, sitedata.blocks(), sitedata.blocks(hicp=True))
    check = Check("gr-x", "gr", "percent", 0.0, {"source": "a"}, {"source": "b"})
    check.comparisons = [
        Comparison("2024-01", 1.0, 1.0, True),
        Comparison("2024-02", 1.0, 1.1, False, "rounding"),
        Comparison("2024-03", 2.0, 2.0, True),
    ]
    monkeypatch.setattr(m5, "all_checks", lambda con, archive, archive_dir, duck: [check])
    monkeypatch.setattr(m5, "all_questions", lambda con: [])
    out_dir = tmp_path / "outputs"
    code, out = run("module5", "run", "--out", str(out_dir))
    lines = out.splitlines()
    assert code == 0
    assert "gr-x: 2 of 3 agree (2024-01 to 2024-03); differ: {'rounding': 1}" in lines
    assert any("survey tables or Eurostat's income limits not in the store yet" in line for line in lines)
    assert (out_dir / "gr" / "m5" / "gr-x.csv").is_file() and (out_dir / "gr" / "m5" / "checks.json").is_file()
