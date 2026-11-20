"""Building, promoting and pruning releases, with fake steps: no network, no npm, no store."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from traceconomics import release
from traceconomics.archive.store import StoreResult
from traceconomics.config import Config, ReleaseConfig

pytestmark = pytest.mark.unit


def config(tmp_path: Path) -> Config:
    site = tmp_path / "site"
    return Config(
        archive_dir=tmp_path / "archive",
        user_agent="test",
        store_dir=tmp_path / "store",
        release=ReleaseConfig(
            enabled=True,
            releases_dir=tmp_path / "releases",
            site_dir=site,
            keep=2,
            production_url="https://example.org",
        ),
    )


class FakeSteps:
    """Records each step; the upload step prints a preview address; steps may fail."""

    def __init__(self, site: Path, fail: str | None = None):
        self.site, self.fail, self.ran, self.argvs, self.envs = site, fail, [], [], {}

    def __call__(self, step, env, log: Path) -> int:
        self.ran.append(step.name)
        self.argvs.append(step.argv)
        self.envs[step.name] = env
        text = f"$ {' '.join(step.argv)}\n"
        if step.name == "site-check":
            (self.site / "dist" / "en").mkdir(parents=True, exist_ok=True)
            (self.site / "dist" / "en" / "index.html").write_text("<p>ok</p>", encoding="utf-8")
            meta = self.site / "dist" / release.METADATA
            meta.parent.mkdir(parents=True, exist_ok=True)
            meta.write_text(json.dumps({"generated_at": log.parent.parent.name}), encoding="utf-8")
        if step.name in ("upload", "promote"):
            alias = step.argv[step.argv.index("--preview-alias") + 1] if "--preview-alias" in step.argv else "x"
            text += (
                "Worker Version ID: 1234\nVersion Preview URL: https://ab12cd34-traceconomics.example.workers.dev\n"
                f"Version Preview Alias URL: https://{alias}-traceconomics.example.workers.dev\n"
            )
        if step.name == "series":
            out = Path(step.argv[step.argv.index("--out") + 1]) / "gr" / "m1"
            out.mkdir(parents=True)
            (out / "m1_index.csv").write_text("x\n", encoding="utf-8")
        log.write_text(text + ("boom\n" if step.name == self.fail else ""), encoding="utf-8")
        return 1 if step.name == self.fail else 0


@pytest.fixture(autouse=True)
def host(monkeypatch, tmp_path):
    """A host that serves each promoted build's own files at once; records the addresses asked."""
    asked = []

    def fetch(url, user_agent):
        asked.append(url)
        assert user_agent == "test"  # the config's, never Python's default
        build_id = url.rsplit("promote=", 1)[1]
        return (tmp_path / "releases" / build_id / "dist" / release.METADATA).read_bytes()

    monkeypatch.setattr(release, "_fetch", fetch)
    return asked


@pytest.fixture(autouse=True)
def no_email(monkeypatch):
    sent = []
    monkeypatch.setattr(release, "notify", lambda cfg, subject, body: sent.append((subject, body)) or "outbox")
    return sent


def test_a_good_build_keeps_everything_and_reports_the_preview(tmp_path, no_email):
    """PY-REL-001: a good release build keeps its files and reports the preview

    Given a configuration with release builds on and steps that all succeed
    When a release build runs
    Then it is ok, with an id from the build's UTC time
    And the steps run in order: inputs, store, series, bands, store-bands, check-v1, check-v1-cpi, check-combos, check-weights, consistency, export, check-figures, npm-ci, site-check, ui-test, upload, smoke
    And the preview address is the build's alias address
    And the build folder's SHA256SUMS lists the site files and the outputs
    And its release.json records the result ok
    And the email says the build is ready for review and gives the promote command for it
    """
    cfg = config(tmp_path)
    fake = FakeSteps(cfg.release.site_dir)
    rec = release.build(cfg, now=datetime(2026, 11, 10, 11, 30, tzinfo=UTC), runner=fake)
    assert rec["result"] == "ok" and rec["id"] == "20261110T113000Z"
    assert fake.ran == [
        "inputs",
        "store",
        "series",
        "bands",
        "store-bands",
        "check-v1",
        "check-v1-cpi",
        "check-combos",
        "check-weights",
        "consistency",
        "export",
        "check-figures",
        "npm-ci",
        "site-check",
        "ui-test",
        "upload",
        "smoke",
    ]
    folder = cfg.release.releases_dir / rec["id"]
    assert rec["preview_url"] == "https://build-20261110t113000z-traceconomics.example.workers.dev"
    sums = (folder / "SHA256SUMS").read_text(encoding="utf-8")
    assert "  dist/en/index.html" in sums and "  outputs/gr/m1/m1_index.csv" in sums
    assert json.loads((folder / "release.json").read_text(encoding="utf-8"))["result"] == "ok"
    subject, body = no_email[0]
    assert "ready for review" in subject and f"release promote {rec['id']}" in body


def test_a_failed_step_stops_the_build_and_raises_an_alert(tmp_path, no_email):
    """PY-REL-002: a failed step stops the release build and raises an alert

    Given steps where check-v1 fails
    When a release build runs
    Then it fails at check-v1
    And no step runs after it, so nothing is uploaded
    And the record keeps the tail of the step's log
    And an alert email names the failed step
    """
    cfg = config(tmp_path)
    fake = FakeSteps(cfg.release.site_dir, fail="check-v1")
    rec = release.build(cfg, now=datetime(2026, 11, 10, 11, 30, tzinfo=UTC), runner=fake)
    assert rec["result"] == "failed" and rec["failed_step"] == "check-v1"
    assert fake.ran[-1] == "check-v1" and "upload" not in fake.ran
    assert "boom" in rec["log_tail"]
    assert no_email[0][0].startswith("ALERT: release") and "check-v1" in no_email[0][0]


def test_stale_survey_tables_stop_the_build_before_anything_reads_them(tmp_path, no_email):
    """PY-REL-025: stale survey tables stop the build at its first step

    Given steps where the inputs check fails (survey tables older than the code or their files)
    When a release build runs
    Then it fails at inputs, the first step, running `check inputs`
    And no other step runs: nothing reads the tables, nothing is uploaded
    And an alert email names the inputs step
    And the build can't be retested: stale tables need a rebuild, then a new build
    """
    cfg = config(tmp_path)
    fake = FakeSteps(cfg.release.site_dir, fail="inputs")
    rec = release.build(cfg, now=datetime(2026, 11, 10, 11, 30, tzinfo=UTC), runner=fake)
    assert rec["result"] == "failed" and rec["failed_step"] == "inputs"
    assert fake.ran == ["inputs"] and fake.argvs[0][-2:] == ("check", "inputs")
    assert no_email[0][0].startswith("ALERT: release") and "inputs" in no_email[0][0]
    assert "inputs" not in release.RETESTABLE


def test_upload_is_a_preview_version_named_from_the_config(tmp_path):
    """PY-REL-003: the upload is a preview version named from the configuration

    Given a release configuration
    When the steps of a build are listed
    Then the upload step runs wrangler's "versions upload" through npx without installing
    And its preview alias is the lower-cased build id with a "build-" prefix
    And it uploads to the worker named traceconomics
    And it uploads the site's built files
    """
    cfg = config(tmp_path)
    up = next(s for s in release.steps(cfg, tmp_path / "r", "20261110T113000Z") if s.name == "upload")
    assert up.argv[:5] == ("npx", "--no-install", "wrangler", "versions", "upload")
    assert up.argv[up.argv.index("--preview-alias") + 1] == "build-20261110t113000z"
    assert up.argv[up.argv.index("--name") + 1] == "traceconomics"
    assert up.argv[up.argv.index("--assets") + 1] == str(cfg.release.site_dir / "dist")


def test_release_builds_carry_the_visit_count_beacon(monkeypatch):
    # The site's build adds the beacon only when this is set: never in local builds or tests.
    """PY-REL-004: release builds turn on the visit-count beacon

    Given no analytics setting in the environment
    When a release step's environment is made
    Then TRACECONOMICS_ANALYTICS is "on"
    """
    monkeypatch.delenv("TRACECONOMICS_ANALYTICS", raising=False)
    assert release._env(None)["TRACECONOMICS_ANALYTICS"] == "on"


def test_only_a_good_build_can_be_promoted_and_it_becomes_the_baseline(tmp_path):
    """PY-REL-005: a failed build can't be promoted

    Given a build that failed at the series step
    When it is promoted to staging
    Then the promote is refused
    And no promote record is written
    """
    cfg = config(tmp_path)
    bad = release.build(
        cfg, now=datetime(2026, 11, 4, tzinfo=UTC), runner=FakeSteps(cfg.release.site_dir, fail="series")
    )
    with pytest.raises(SystemExit):
        release.promote(cfg, bad["id"], "staging", runner=FakeSteps(cfg.release.site_dir))
    assert not (cfg.release.releases_dir / release.PROMOTED).exists()


def test_a_promoted_good_build_becomes_the_baseline(tmp_path):
    """PY-REL-023: a promoted good build uploads its own files and becomes the baseline

    Given a build that failed at the series step, then a good build
    When the good build is promoted to staging
    Then the promote records staging and its preview alias address
    And the last command uploads that build's own files as a version
    And that build, not the failed one, is the baseline for the next build
    """
    cfg = config(tmp_path)
    release.build(cfg, now=datetime(2026, 11, 4, tzinfo=UTC), runner=FakeSteps(cfg.release.site_dir, fail="series"))
    good = release.build(cfg, now=datetime(2026, 11, 10, tzinfo=UTC), runner=FakeSteps(cfg.release.site_dir))
    fake = FakeSteps(cfg.release.site_dir)
    done = release.promote(cfg, good["id"], "staging", runner=fake)
    assert done["to"] == "staging" and done["url"] == "https://staging-traceconomics.example.workers.dev"
    assert "versions" in fake.argvs[-1] and str(cfg.release.releases_dir / good["id"] / "dist") in fake.argvs[-1]
    assert release.baseline(cfg.release.releases_dir)["id"] == good["id"]


def test_pruning_keeps_the_newest_and_the_promoted_build(tmp_path):
    """PY-REL-006: pruning keeps the newest builds and the promoted one

    Given a configuration that keeps two builds
    And a promoted build followed by three more
    When the builds are pruned after each build
    Then the promoted build and the two newest are left
    """
    cfg = config(tmp_path)
    ids = [
        release.build(cfg, now=datetime(2026, 11, d, tzinfo=UTC), runner=FakeSteps(cfg.release.site_dir))["id"]
        for d in (1, 2)
    ]
    release.promote(cfg, ids[0], "staging", runner=FakeSteps(cfg.release.site_dir))
    for d in (3, 4):
        release.build(cfg, now=datetime(2026, 11, d, tzinfo=UTC), runner=FakeSteps(cfg.release.site_dir))
    left = sorted(p.name for p in cfg.release.releases_dir.iterdir() if p.is_dir() and p.name != "state")
    assert left == [ids[0], "20261103T000000Z", "20261104T000000Z"]


def test_changes_since_the_last_release(tmp_path):
    """PY-REL-007: the changes since the last release are counted

    Given an old and a new set of rate outputs, where the new one revises one month by 0.1 points and adds a month
    When the changes are computed
    Then the latest period is the added month, listed as the one new period, with one new value
    And one value was revised, by 0.1 points at most
    """
    duckdb = pytest.importorskip("duckdb")
    cols = 'geo, grouping, "group", spending, imputed_rent, price_source, weights_timing, tutoring, coicop18, unit, ref_period, value_text'

    def write(folder, rows):
        (folder / "gr" / "m1").mkdir(parents=True)
        values = ", ".join(
            f"('GR', 'B', 'Q1', 'purchases', 'excluded', 'cpi', 'N', 'priced', 'TOTAL', 'RCH_A', '{p}', '{v}')"
            for p, v in rows
        )
        duckdb.sql(
            f"COPY (SELECT * FROM (VALUES {values}) t({cols})) TO '{(folder / 'gr' / 'm1' / 'm1_rates.parquet').as_posix()}'"
        )

    write(tmp_path / "old", [("2026-08", "3.1"), ("2026-09", "2.9")])
    write(tmp_path / "new", [("2026-08", "3.1"), ("2026-09", "3.0"), ("2026-10", "2.7")])
    c = release.changes(tmp_path / "old", tmp_path / "new")
    assert c["latest_period"] == "2026-10" and c["new_periods"] == ["2026-10"] and c["new_values"] == 1
    assert c["revised_values"] == 1 and abs(c["largest_revision_pp"] - 0.1) < 1e-9


def test_only_files_that_feed_the_store_trigger_a_release(tmp_path):
    """PY-REL-008: only newly stored files that feed the store trigger a release

    Given a run that stored a HICP file and a calendar page, and found another HICP file unchanged
    When the files that feed the store are picked
    Then only the stored HICP dataset is listed
    """

    def stored(source, dataset, name=None):
        folder = tmp_path / source / dataset
        folder.mkdir(parents=True)
        (folder / "manifest.json").write_text(json.dumps({"original_name": name}), encoding="utf-8")
        return StoreResult("stored", source, dataset, "0" * 64, folder / "payload.bin")

    results = [
        stored("eurostat", "prc_hicp_minr"),
        stored("elstat", "calendar"),
        StoreResult("unchanged", "eurostat", "prc_hicp_iw", "0" * 64, None),
    ]
    assert release.feeds_store(None, results) == ["eurostat/prc_hicp_minr"]


def test_promoting_to_production_publishes_on_the_public_address(tmp_path, host):
    """PY-REL-009: a promote to production deploys the build and checks it on the public address

    Given a good build, and a configuration whose public address is https://example.org
    When it is promoted to production
    Then the last command is wrangler's deploy through npx without installing, not a preview upload
    And the promote is checked on the public address, and recorded with it
    """
    cfg = config(tmp_path)
    good = release.build(cfg, now=datetime(2026, 11, 10, tzinfo=UTC), runner=FakeSteps(cfg.release.site_dir))
    fake = FakeSteps(cfg.release.site_dir)
    done = release.promote(cfg, good["id"], "production", runner=fake)
    assert fake.argvs[-1][:4] == ("npx", "--no-install", "wrangler", "deploy")
    assert "--preview-alias" not in fake.argvs[-1]
    assert host[-1] == f"https://example.org/{release.METADATA}?promote={good['id']}"
    assert done["url"] == "https://example.org" and "confirmed" in done
    assert release.promoted(cfg.release.releases_dir)["production"]["url"] == "https://example.org"


def test_a_promote_to_an_unknown_target_is_refused(tmp_path):
    """PY-REL-010: a promote to an unknown target is refused

    Given a good build
    When it is promoted to "preview", which is not a target
    Then the promote is refused
    And no promote record is written
    """
    cfg = config(tmp_path)
    good = release.build(cfg, now=datetime(2026, 11, 10, tzinfo=UTC), runner=FakeSteps(cfg.release.site_dir))
    with pytest.raises(SystemExit):
        release.promote(cfg, good["id"], "preview", runner=FakeSteps(cfg.release.site_dir))
    assert not (cfg.release.releases_dir / release.PROMOTED).exists()


def test_staging_and_production_serve_their_own_builds(tmp_path):
    """PY-REL-011: staging and production serve their own builds

    Given two good builds, the first promoted to production and the second to staging
    When the promote records are read
    Then production shows the first build and staging the second
    And the baseline for the next build is the production build
    And the status lists each build with the target it is on
    And after three more builds and pruning, both promoted builds are still kept
    """
    cfg, keep = config(tmp_path), FakeSteps(tmp_path / "site")
    ids = [release.build(cfg, now=datetime(2026, 11, d, tzinfo=UTC), runner=keep)["id"] for d in (1, 2)]
    release.promote(cfg, ids[0], "production", runner=keep)
    release.promote(cfg, ids[1], "staging", runner=keep)
    on = release.promoted(cfg.release.releases_dir)
    assert on["production"]["id"] == ids[0] and on["staging"]["id"] == ids[1]
    # The public site is what the next build is compared with.
    assert release.baseline(cfg.release.releases_dir)["id"] == ids[0]
    assert {b["id"]: b["on"] for b in release.status(cfg.release.releases_dir)} == {
        ids[1]: ["staging"],
        ids[0]: ["production"],
    }
    for d in (3, 4, 5):
        release.build(cfg, now=datetime(2026, 11, d, tzinfo=UTC), runner=keep)
    left = sorted(p.name for p in cfg.release.releases_dir.iterdir() if (p / "release.json").is_file())
    assert set(ids) <= set(left)


def test_a_promote_record_from_before_targets_reads_as_staging(tmp_path):
    """PY-REL-012: a promote record from before targets reads as staging

    Given an old single promote record
    When the promote records are read
    Then it shows as the staging build
    And it is the baseline
    """
    folder = tmp_path / "releases"
    folder.mkdir()
    (folder / release.PROMOTED).write_text(json.dumps({"id": "20261028T155928Z", "to": "staging"}), encoding="utf-8")
    assert release.promoted(folder) == {"staging": {"id": "20261028T155928Z", "to": "staging"}}
    assert release.baseline(folder)["id"] == "20261028T155928Z"


def test_the_browser_tests_run_before_upload_and_again_on_the_preview(tmp_path):
    """PY-REL-013: the browser tests run before the upload and again on the preview

    Given steps that all succeed
    When a release build runs
    Then the ui-test step has no BASE_URL, so it tests the built files on a local server
    And it runs the full suite, with no --grep
    And the smoke step runs only the tests tagged @smoke
    And it runs against the build's preview address
    And it writes its report into the build's folder
    """
    cfg = config(tmp_path)
    fake = FakeSteps(cfg.release.site_dir)
    rec = release.build(cfg, now=datetime(2026, 11, 10, tzinfo=UTC), runner=fake)
    folder = cfg.release.releases_dir / rec["id"]
    assert "BASE_URL" not in fake.envs["ui-test"]  # a local server on the built files
    argv = dict(zip(fake.ran, fake.argvs, strict=True))
    assert "--grep" not in argv["ui-test"]  # the full suite before upload
    assert argv["smoke"][-2:] == ("--grep", "@smoke")  # the short set on the preview
    assert fake.envs["smoke"]["BASE_URL"] == rec["preview_url"]
    assert fake.envs["smoke"]["UI_REPORT"] == str(folder / "ui" / "smoke" / "report")


def test_a_build_held_back_by_its_browser_tests_publishes_nothing_and_keeps_its_files(tmp_path, no_email):
    """PY-REL-014: a build held back by its browser tests publishes nothing and keeps its files

    Given steps where ui-test fails
    When a release build runs
    Then it fails at ui-test and nothing is uploaded
    And the build folder keeps its site files
    And the email says it failed at ui-test, that nothing was published, and points to release retest
    And a promote of the build is refused
    """
    cfg = config(tmp_path)
    fake = FakeSteps(cfg.release.site_dir, fail="ui-test")
    rec = release.build(cfg, now=datetime(2026, 11, 10, tzinfo=UTC), runner=fake)
    assert rec["failed_step"] == "ui-test" and "upload" not in fake.ran
    assert (cfg.release.releases_dir / rec["id"] / "dist" / "en" / "index.html").is_file()
    subject, body = no_email[0]
    assert "failed at ui-test" in subject and "Nothing was published" in body and "release retest" in body
    with pytest.raises(SystemExit):
        release.promote(cfg, rec["id"], "staging", runner=FakeSteps(cfg.release.site_dir))


def test_a_retest_runs_the_rest_on_the_files_the_build_made(tmp_path, no_email):
    """PY-REL-015: a retest runs the remaining steps on the build's own files

    Given a build held back at ui-test
    And a later build's files left in the site folder
    When the build is retested
    Then ui-test, upload and smoke run, and ui-test sees the held-back build's files
    And the build is now ok, with no failed step and a passing retest recorded
    And its preview address is the build's alias address
    And the email says it passed its retest
    And it can then be promoted to staging
    """
    cfg = config(tmp_path)
    rec = release.build(
        cfg, now=datetime(2026, 11, 10, tzinfo=UTC), runner=FakeSteps(cfg.release.site_dir, fail="ui-test")
    )
    # A later build left other files in the site folder; the retest must test this build's.
    (cfg.release.site_dir / "dist" / "en" / "index.html").write_text("<p>a later build</p>", encoding="utf-8")
    fake = FakeSteps(cfg.release.site_dir)
    seen = []

    def fake_ui(step, env, log):
        return seen.append((cfg.release.site_dir / "dist" / "en" / "index.html").read_text()) or fake(step, env, log)

    again = release.retest(cfg, rec["id"], runner=fake_ui, now=datetime(2026, 11, 10, 12, tzinfo=UTC))
    assert fake.ran == ["ui-test", "upload", "smoke"] and seen[0] == "<p>ok</p>"
    assert again["result"] == "ok" and "failed_step" not in again and again["retests"][0]["result"] == "ok"
    assert again["preview_url"] == "https://build-20261110t000000z-traceconomics.example.workers.dev"
    assert "passed its retest" in no_email[-1][0]
    release.promote(cfg, rec["id"], "staging", runner=FakeSteps(cfg.release.site_dir))


def test_a_retest_after_the_upload_tests_the_version_already_uploaded(tmp_path):
    """PY-REL-016: a retest after the upload tests the version already uploaded

    Given a build that failed at smoke, after its upload
    When it is retested
    Then only ui-test and smoke run, with no new upload
    """
    cfg = config(tmp_path)
    rec = release.build(
        cfg, now=datetime(2026, 11, 10, tzinfo=UTC), runner=FakeSteps(cfg.release.site_dir, fail="smoke")
    )
    fake = FakeSteps(cfg.release.site_dir)
    release.retest(cfg, rec["id"], runner=fake, now=datetime(2026, 11, 10, 12, tzinfo=UTC))
    assert fake.ran == ["ui-test", "smoke"]


def test_a_retest_refuses_what_a_retest_cant_fix(tmp_path):
    """PY-REL-017: a retest refuses what a retest can't fix

    Given a good build, a build that failed at check-v1, an unknown build id
    And a build held back at ui-test whose browser tests have changed since
    When each is retested
    Then the good build is refused as already passed
    And the check-v1 failure is refused with advice to build again
    And the unknown id is refused as no release
    And the held-back build is refused because the tests are not the ones it ran
    """
    cfg = config(tmp_path)
    for day, fail, why in ((1, None, "already passed"), (2, "check-v1", "build again")):
        rec = release.build(
            cfg, now=datetime(2026, 11, day, tzinfo=UTC), runner=FakeSteps(cfg.release.site_dir, fail=fail)
        )
        with pytest.raises(SystemExit, match=why):
            release.retest(cfg, rec["id"], runner=FakeSteps(cfg.release.site_dir))
    with pytest.raises(SystemExit, match="no release"):
        release.retest(cfg, "20990101T000000Z", runner=FakeSteps(cfg.release.site_dir))
    held = release.build(
        cfg, now=datetime(2026, 11, 3, tzinfo=UTC), runner=FakeSteps(cfg.release.site_dir, fail="ui-test")
    )
    # Tests changed since the build: they aren't the ones it ran.
    (cfg.release.site_dir / "tests" / "ui").mkdir(parents=True)
    (cfg.release.site_dir / "tests" / "ui" / "smoke.ui.ts").write_text("// changed", encoding="utf-8")
    with pytest.raises(SystemExit, match="not the ones"):
        release.retest(cfg, held["id"], runner=FakeSteps(cfg.release.site_dir))


def test_a_promote_is_confirmed_only_when_the_target_serves_the_build(tmp_path, host):
    """PY-REL-018: a promote is confirmed when the target serves the build

    Given a good build and a host that serves each promoted build's files
    When it is promoted to production
    Then the promote's address is the public address and it is confirmed
    And the only address checked was the public address's build metadata for that build
    """
    cfg = config(tmp_path)
    good = release.build(cfg, now=datetime(2026, 11, 10, tzinfo=UTC), runner=FakeSteps(cfg.release.site_dir))
    done = release.promote(cfg, good["id"], "production", runner=FakeSteps(cfg.release.site_dir))
    assert done["url"] == "https://example.org" and "confirmed" in done
    assert host == [f"https://example.org/{release.METADATA}?promote={good['id']}"]


def test_a_promote_is_refused_while_the_target_serves_another_build(tmp_path, host):
    """PY-REL-024: a promote is refused while the target serves another build

    Given a good build, already promoted to production and confirmed there
    When it is promoted to staging while the host serves another build
    Then the promote is refused, saying the target doesn't serve it
    And it waited the confirm interval for the whole confirm time between checks
    And the staging record is unconfirmed while production stays confirmed
    """
    cfg = config(tmp_path)
    good = release.build(cfg, now=datetime(2026, 11, 10, tzinfo=UTC), runner=FakeSteps(cfg.release.site_dir))
    release.promote(cfg, good["id"], "production", runner=FakeSteps(cfg.release.site_dir))
    naps = []
    with pytest.raises(SystemExit, match="doesn't serve it"):
        release.promote(
            cfg,
            good["id"],
            "staging",
            runner=FakeSteps(cfg.release.site_dir),
            fetch=lambda url: b'{"generated_at": "another build"}',
            sleep=naps.append,
        )
    assert naps == [release.CONFIRM_EVERY] * (release.CONFIRM_FOR // release.CONFIRM_EVERY)
    on = release.promoted(cfg.release.releases_dir)
    assert "unconfirmed" in on["staging"] and "confirmed" in on["production"]


def test_a_promote_to_production_needs_the_public_address(tmp_path):
    """PY-REL-019: a promote to production needs the public address

    Given a good build and a release configuration with no production address
    When it is promoted to production
    Then the promote is refused, naming production_url
    And no step ran, so nothing was uploaded
    """
    cfg = config(tmp_path)
    good = release.build(cfg, now=datetime(2026, 11, 10, tzinfo=UTC), runner=FakeSteps(cfg.release.site_dir))
    bare = Config(
        archive_dir=cfg.archive_dir,
        user_agent="test",
        release=ReleaseConfig(enabled=True, releases_dir=cfg.release.releases_dir, site_dir=cfg.release.site_dir),
    )
    fake = FakeSteps(cfg.release.site_dir)
    with pytest.raises(SystemExit, match="production_url"):
        release.promote(bare, good["id"], "production", runner=fake)
    assert fake.ran == []  # refused before anything was uploaded


def test_the_public_address_is_read_from_the_config_without_a_trailing_slash(tmp_path):
    """PY-REL-020: the public address is read from the configuration without a trailing slash

    Given a configuration whose production address ends in a slash
    When it is parsed
    Then the production address has no trailing slash
    And a configuration with no release section has no production address
    """
    from traceconomics.config import parse

    base = {"archive": {"dir": str(tmp_path)}, "fetch": {"user_agent": "test"}}
    c = parse(
        {**base, "release": {"site_dir": str(tmp_path / "site"), "production_url": "https://example.org/"}}, tmp_path
    )
    assert c.release.production_url == "https://example.org"
    assert parse(base, tmp_path).release.production_url is None


PLAYWRIGHT_RESULTS = {
    "suites": [
        {
            "title": "smoke.ui.ts",
            "specs": [
                {"title": "/en/ loads", "tests": [{"status": "expected", "results": [{"status": "passed"}]}]},
            ],
            "suites": [
                {
                    "title": "on the host",
                    "specs": [
                        {
                            "title": "pages carry the security headers",
                            "tests": [
                                {
                                    "status": "unexpected",
                                    "results": [
                                        {
                                            "status": "failed",
                                            "error": {
                                                "message": "\u001b[2mexpect(\u001b[22mreceived).toContain()\n\nExpected substring"
                                            },
                                        }
                                    ],
                                }
                            ],
                        },
                    ],
                }
            ],
        }
    ],
    "errors": [{"message": "Error: Timed out waiting 60000ms from config.webServer."}],
}


def test_the_failing_browser_tests_are_named_from_their_results_file(tmp_path):
    """PY-REL-021: the failing browser tests are named from their results file

    Given a Playwright results file with a passing test, a failing nested test and an error outside the tests
    When the failures are read
    Then the failing test is named by its file, suite and title, with its error's first line free of colour codes
    And the error outside the tests is listed as such
    And a missing results file gives no failures
    """
    results = tmp_path / "results.json"
    results.write_text(json.dumps(PLAYWRIGHT_RESULTS), encoding="utf-8")
    assert release.ui_failures(results) == [
        "smoke.ui.ts › on the host › pages carry the security headers: expect(received).toContain()",
        "(outside the tests): Error: Timed out waiting 60000ms from config.webServer.",
    ]
    assert release.ui_failures(tmp_path / "missing.json") == []


def test_a_browser_test_failure_email_names_the_tests_and_the_report(tmp_path, no_email):
    """PY-REL-022: a browser-test failure email names the tests and the report

    Given steps where ui-test fails and writes a results file
    When a release build runs
    Then the record points to the HTML report in the build's folder
    And the alert email lists the failing browser tests and the report's path
    And after a retest that passes, the record no longer has failures or a report
    """
    cfg = config(tmp_path)

    class WritesResults(FakeSteps):
        def __call__(self, step, env, log):
            if step.name == "ui-test":
                Path(env["UI_JSON"]).parent.mkdir(parents=True, exist_ok=True)
                Path(env["UI_JSON"]).write_text(json.dumps(PLAYWRIGHT_RESULTS), encoding="utf-8")
            return super().__call__(step, env, log)

    rec = release.build(
        cfg, now=datetime(2026, 11, 10, tzinfo=UTC), runner=WritesResults(cfg.release.site_dir, fail="ui-test")
    )
    folder = cfg.release.releases_dir / rec["id"]
    assert rec["ui_report"] == str(folder / "ui" / "ui-test" / "report" / "index.html")
    body = no_email[0][1]
    assert "Failing browser tests:" in body and "pages carry the security headers" in body and rec["ui_report"] in body
    # A retest that passes clears them.
    again = release.retest(
        cfg, rec["id"], runner=FakeSteps(cfg.release.site_dir), now=datetime(2026, 11, 10, 12, tzinfo=UTC)
    )
    assert "ui_failures" not in again and "ui_report" not in again


# -- automatic promotes (release_decision) ------------------------------------

COMMIT = "c0ffee" * 7
SETTING = {
    "spending": "purchases",
    "imputed_rent": "excluded",
    "price_source": "cpi",
    "weights_timing": "N",
    "tutoring": "priced",
    "unit": "RCH_A",
    "coicop18": "TOTAL",
}
SEPT = {("all", "all"): {"2026-08": 3.0, "2026-09": 3.0}, ("B", "Q1"): {"2026-08": 3.5, "2026-09": 3.6}}
OCT = {k: {**v, "2026-10": v["2026-09"] + 0.1} for k, v in SEPT.items()}
CPI_SEPT = {"archive_dataset": "elstat/doc-585819", "sha256": "a" * 64}
CPI_OCT = {"archive_dataset": "elstat/doc-585819", "sha256": "c" * 64}
WEIGHTS = {"archive_dataset": "oet-local/hbs-weights-gr-2024", "sha256": "b" * 64}


def write_rates(path: Path, series: dict) -> None:
    """A rates file as the outputs write it: every column text, the value with its full digits."""
    import duckdb

    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {**SETTING, "grouping": g, "group": q, "ref_period": p, "value": repr(v), "value_text": f"{v:.1f}"}
        for (g, q), months in series.items()
        for p, v in months.items()
    ]
    con = duckdb.connect()
    con.execute(
        "CREATE TABLE r (spending TEXT, imputed_rent TEXT, price_source TEXT, weights_timing TEXT, tutoring TEXT, "
        'unit TEXT, coicop18 TEXT, grouping TEXT, "group" TEXT, ref_period TEXT, value TEXT, value_text TEXT)'
    )
    cols = ["spending", "imputed_rent", "price_source", "weights_timing", "tutoring", "unit", "coicop18"]
    cols += ["grouping", "group", "ref_period", "value", "value_text"]
    con.executemany(f"INSERT INTO r VALUES ({', '.join('?' * len(cols))})", [[r[c] for c in cols] for r in rows])
    con.execute(f"COPY r TO '{path.as_posix()}' (FORMAT parquet)")


class DataSteps(FakeSteps):
    """Fake steps whose store holds the given archived files and whose series step writes the given rates."""

    def __init__(self, cfg: Config, rates: dict, loaded: list[dict], fail: str | None = None):
        super().__init__(cfg.release.site_dir, fail)
        self.store, self.rates, self.loaded = cfg.store_dir, rates, loaded

    def __call__(self, step, env, log: Path) -> int:
        code = super().__call__(step, env, log)
        if step.name == "store":
            self.store.mkdir(parents=True, exist_ok=True)
            text = "".join(json.dumps(x) + "\n" for x in self.loaded)
            (self.store / "loaded.jsonl").write_text(text, encoding="utf-8")
        if step.name == "series":
            write_rates(Path(step.argv[step.argv.index("--out") + 1]) / "gr" / "m1" / "m1_rates.parquet", self.rates)
        return code


def auto_config(tmp_path: Path, mode: str) -> Config:
    cfg = config(tmp_path)
    return Config(
        **{**cfg.__dict__, "release": ReleaseConfig(**{**cfg.release.__dict__, "auto_promote": mode, "keep": 3})}
    )


@pytest.fixture
def on_production(tmp_path, monkeypatch):
    """September's build, live on production; every build's commit is the same."""
    monkeypatch.setattr(release.testresults, "source_commit", lambda _: COMMIT)
    cfg = auto_config(tmp_path, "off")
    first = release.build(
        cfg, now=datetime(2026, 10, 9, 11, tzinfo=UTC), runner=DataSteps(cfg, SEPT, [CPI_SEPT, WEIGHTS])
    )
    release.promote(cfg, first["id"], "production", runner=FakeSteps(cfg.release.site_dir))
    return first["id"]


# ELSTAT's October CPI: 12:00 Greek time on 2026-11-10.
RELEASED = datetime(2026, 11, 10, 10, tzinfo=UTC)


def october(tmp_path, mode, loaded=(CPI_SEPT, CPI_OCT, WEIGHTS), rates=OCT, fail=None, released=RELEASED):
    cfg = auto_config(tmp_path, mode)
    steps = DataSteps(cfg, rates, list(loaded), fail)
    now = datetime(2026, 11, 10, 11, tzinfo=UTC)
    return cfg, steps, release.build(cfg, now=now, runner=steps, released=released)


def test_shadow_mode_says_it_would_promote_and_promotes_nothing(tmp_path, on_production, no_email):
    """PY-REL-026: in shadow mode a data-only build's email says it would promote, and nothing is promoted

    Given September's build on production, and the same code
    When October's build runs in shadow mode with ELSTAT's new file and a new month, nothing revised
    Then its email's subject says it would promote, and production still serves September's build
    And the report shows the decision against production's build
    And the build records its decision and the archived files its store held
    """
    cfg, _, rec = october(tmp_path, "shadow")
    subject, body = no_email[-1]
    assert subject == f"release {rec['id']} ready for review (shadow: would promote)"
    assert release.promoted(cfg.release.releases_dir)["production"]["id"] == on_production
    assert f"Automatic promote (shadow: nothing was promoted), against production's build {on_production}" in body
    assert rec["decision"]["verdict"] == "promote" and rec["decision"]["mode"] == "shadow"
    inputs = json.loads((cfg.release.releases_dir / rec["id"] / "inputs.json").read_text(encoding="utf-8"))
    assert inputs == {"elstat/doc-585819": ["a" * 64, "c" * 64], "oet-local/hbs-weights-gr-2024": ["b" * 64]}


def test_a_data_only_build_goes_live_by_itself_and_names_the_way_back(tmp_path, on_production, no_email):
    """PY-REL-027: with automatic promotes on, a data-only build goes to production and the email names the way back

    Given September's build on production, and the same code
    When October's build runs with automatic promotes on, with ELSTAT's new file and a new month
    Then it is promoted to production, which serves it, and records September's build as the one it replaced
    And the email's subject says it is live
    And the email names September's build and the command that puts it back
    """
    cfg, steps, rec = october(tmp_path, "on")
    on = release.promoted(cfg.release.releases_dir)["production"]
    assert on["id"] == rec["id"] and on["previous"] == on_production and on["confirmed"]
    assert "promote" in steps.ran
    subject, body = no_email[-1]
    assert subject == f"PROMOTED: release {rec['id']} is live (only the publishers' data changed)"
    assert f"To go back: traceconomics release promote {on_production} --to production" in body
    assert "To publish it" not in body


@pytest.mark.parametrize(
    "loaded, rates, reason",
    [
        ((CPI_SEPT, CPI_OCT, {**WEIGHTS, "sha256": "d" * 64}), OCT, "our own tables changed"),
        ((CPI_SEPT, WEIGHTS), OCT, "nothing new"),
        (
            (CPI_SEPT, CPI_OCT, WEIGHTS),
            {**OCT, ("B", "Q1"): {**OCT[("B", "Q1")], "2026-09": 3.7}},
            "1 published values revised",
        ),
        (
            (CPI_SEPT, CPI_OCT, WEIGHTS),
            {**OCT, ("B", "Q1"): {**OCT[("B", "Q1")], "2026-10": 5.0}},
            "B/Q1 2026-10: gap to all households",
        ),
    ],
    ids=["own table rebuilt", "nothing new", "a value revised", "beyond a record"],
)
def test_anything_else_holds_the_build_and_says_why(tmp_path, on_production, no_email, loaded, rates, reason):
    """PY-REL-028: with automatic promotes on, any other build waits for the owner, and the email's subject says why

    Given September's build on production, and the same code
    When October's build runs with a rebuilt own table, or nothing new, or September's value revised, or a group beyond its record
    Then production still serves September's build
    And the email's subject starts with HOLD and names the reason
    And the report keeps the command to promote it by hand
    """
    cfg, _, rec = october(tmp_path, "on", loaded=loaded, rates=rates)
    assert release.promoted(cfg.release.releases_dir)["production"]["id"] == on_production
    subject, body = no_email[-1]
    assert subject.startswith(f"HOLD: release {rec['id']} waits for you: ") and reason in subject
    assert f"traceconomics release promote {rec['id']} --to staging" in body


def test_a_production_that_serves_another_build_holds(tmp_path, on_production, no_email, monkeypatch):
    """PY-REL-029: when production doesn't serve the build its record names, the build holds

    Given September's build on record as production's, but the public address serving other files
    When October's build runs with automatic promotes on
    Then it holds, saying production doesn't serve its recorded build
    """
    monkeypatch.setattr(release, "_fetch", lambda url, ua: b'{"generated_at": "someone else"}')
    _, _, rec = october(tmp_path, "on")
    assert rec["decision"]["verdict"] == "hold"
    assert any("production doesn't serve its recorded build" in r for r in rec["decision"]["reasons"])


def test_a_failed_automatic_promote_raises_an_alert(tmp_path, on_production, no_email):
    """PY-REL-030: an automatic promote whose upload fails raises an alert, and production is unchanged

    Given September's build on production
    When October's data-only build is to go live by itself, and the promote's upload fails
    Then production still serves September's build
    And the email's subject is an ALERT saying the promote failed
    """
    cfg, _, rec = october(tmp_path, "on", fail="promote")
    assert release.promoted(cfg.release.releases_dir)["production"]["id"] == on_production
    subject, body = no_email[-1]
    assert subject == f"ALERT: release {rec['id']} was to go live by itself, but its promote failed"
    assert "The promote failed: upload failed" in body


def test_the_build_production_replaced_is_kept_for_a_revert(tmp_path):
    """PY-REL-031: the build production replaced is kept on disk, whatever the number of builds kept

    Given production replaced by a newer build, which records the build it replaced
    And more newer builds than the number kept
    When old builds are pruned
    Then the build on production and the one it replaced are both still on disk
    """
    releases = tmp_path / "releases"
    for b in ("20261101T000000Z", "20261102T000000Z", "20261103T000000Z", "20261104T000000Z"):
        (releases / b).mkdir(parents=True)
        (releases / b / "release.json").write_text(json.dumps({"id": b, "result": "ok"}), encoding="utf-8")
    on = {"production": {"id": "20261102T000000Z", "to": "production", "previous": "20261101T000000Z"}}
    (releases / "promoted.json").write_text(json.dumps(on), encoding="utf-8")
    gone = release.prune(releases, keep=1)
    assert gone == ["20261103T000000Z"]
    assert (releases / "20261101T000000Z").is_dir() and (releases / "20261102T000000Z").is_dir()


def seconds_since_release(at: str) -> int:
    return round((datetime.fromisoformat(at) - RELEASED).total_seconds())


def test_a_build_that_goes_live_by_itself_records_its_time_from_the_release(tmp_path, on_production, no_email):
    """PY-REL-032: a build that goes live by itself records and reports its time from the publisher's release to ready and to live

    Given September's build on production, and ELSTAT's October release at 12:00 Greek time
    When October's data-only build goes live by itself
    Then its record holds the release time, when it was ready, and when production served it, with the seconds since the release
    And its email gives both times from the release
    And a build started for no release (by hand) records and reports none
    """
    cfg, _, rec = october(tmp_path, "on")
    saved = json.loads((cfg.release.releases_dir / rec["id"] / "release.json").read_text(encoding="utf-8"))
    assert saved["released"] == "2026-11-10T10:00:00Z"
    assert saved["live"] == release.promoted(cfg.release.releases_dir)["production"]["live"]
    assert saved["live"]["seconds"] == seconds_since_release(saved["live"]["at"]) > 0
    assert saved["ready"] <= saved["live"]["at"]
    _, body = no_email[-1]
    ready, live = (
        release.duration(seconds_since_release(saved[k] if k == "ready" else saved["live"]["at"]))
        for k in ("ready", "live")
    )
    assert f"Released by the publisher 2026-11-10T10:00:00Z; build ready after {ready}, live after {live}" in body
    by_hand = datetime(2026, 11, 11, 9, tzinfo=UTC)
    manual = release.build(cfg, now=by_hand, runner=DataSteps(cfg, OCT, [CPI_SEPT, CPI_OCT, WEIGHTS]))
    assert "released" not in manual and "Released by the publisher" not in no_email[-1][1]


def test_a_build_promoted_by_hand_records_its_time_to_live(tmp_path, no_email):
    """PY-REL-033: a release build promoted by hand records its time to live on production, not on staging

    Given a passing build started for a release at 12:00 Greek time, held for the owner
    When the owner promotes it to staging, then to production
    Then the staging promote records no time to live
    And the production promote records it, in the promote record and the build's own record
    """
    cfg = config(tmp_path)
    rec = release.build(
        cfg, now=datetime(2026, 11, 10, 11, tzinfo=UTC), runner=FakeSteps(cfg.release.site_dir), released=RELEASED
    )
    folder = cfg.release.releases_dir / rec["id"]
    staged = release.promote(cfg, rec["id"], "staging", runner=FakeSteps(cfg.release.site_dir))
    assert "live" not in staged
    done = release.promote(cfg, rec["id"], "production", runner=FakeSteps(cfg.release.site_dir))
    assert done["live"]["seconds"] == seconds_since_release(done["live"]["at"])
    assert json.loads((folder / "release.json").read_text(encoding="utf-8"))["live"] == done["live"]


@pytest.mark.parametrize("seconds, text", [(59, "1 min"), (47 * 60, "47 min"), (2 * 3600 + 5 * 60 + 20, "2 h 05 min")])
def test_a_time_to_live_reads_in_hours_and_minutes(seconds, text):
    """PY-REL-034: a time from the release reads in minutes, with hours from the first hour on

    Given a time from the release in seconds
    When it is written for the email
    Then it reads as whole minutes, with hours once it reaches an hour
    """
    assert release.duration(seconds) == text


def test_a_build_asked_for_while_another_runs_starts_when_it_ends(tmp_path, no_email):
    """PY-REL-035: a poll during a build: the second build is queued, and the running build starts it when it ends

    Given a build running its steps
    When a second build is asked for during its series step, for Eurostat's new data released at 12:00 Greek time
    Then the second is queued, not started and not failed
    And the first, once it ends, has started the second, which names why it was queued and counts from that release
    And nothing is left queued
    """
    cfg = config(tmp_path)
    queued = []

    class Busy(FakeSteps):
        def __call__(self, step, env, log):
            if step.name == "series" and not queued:
                queued.append(release.build(cfg, reason="new data: eurostat/prc_hicp_minr", released=RELEASED))
            return super().__call__(step, env, log)

    first = release.build(cfg, now=datetime(2026, 11, 10, 11, tzinfo=UTC), runner=Busy(cfg.release.site_dir))
    assert queued == [{"id": None, "result": "queued", "reason": "new data: eurostat/prc_hicp_minr"}]
    assert first["result"] == "ok" and first["next"]
    second = json.loads((cfg.release.releases_dir / first["next"] / "release.json").read_text(encoding="utf-8"))
    assert second["reason"] == "queued while another build ran: new data: eurostat/prc_hicp_minr"
    assert second["released"] == "2026-11-10T10:00:00Z" and second["result"] == "ok"
    assert release.take_wanted(cfg.release.releases_dir) is None


def test_builds_queued_together_make_one_build(tmp_path):
    """PY-REL-036: several builds queued while one runs make one build, with every reason, timed from the earliest release

    Given a build queued for ELSTAT's data released at 12:00, then one for Eurostat's released at 12:00 a day later, then the first again
    When the queued build is taken
    Then it names both reasons once each and counts from the earlier release
    And taking it again finds nothing queued
    """
    later = datetime(2026, 11, 11, 10, tzinfo=UTC)
    release.want(tmp_path, "new data: elstat/doc-604757", RELEASED)
    release.want(tmp_path, "new data: eurostat/prc_hicp_minr", later)
    release.want(tmp_path, "new data: elstat/doc-604757", None)
    wanted = release.take_wanted(tmp_path)
    assert wanted == {
        "reason": "queued while another build ran: new data: elstat/doc-604757; new data: eurostat/prc_hicp_minr",
        "released": RELEASED,
    }
    assert release.take_wanted(tmp_path) is None
