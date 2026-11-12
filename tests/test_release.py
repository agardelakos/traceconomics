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
    And the steps run in order: store, series, bands, store-bands, check-v1, check-v1-cpi, check-combos, consistency, export, npm-ci, site-check, ui-test, upload, smoke
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
        "store",
        "series",
        "bands",
        "store-bands",
        "check-v1",
        "check-v1-cpi",
        "check-combos",
        "consistency",
        "export",
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
    argv = dict(zip(fake.ran, fake.argvs))
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
    fake_ui = lambda step, env, log: (
        seen.append((cfg.release.site_dir / "dist" / "en" / "index.html").read_text()) or fake(step, env, log)
    )
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
