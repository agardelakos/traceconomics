"""Release builds' test results, sent to the test-results bucket: what is sent, in which order, and
that a failure to send never stops a build or a promote. Fake uploads only: no network."""

import http.client
import json
import urllib.error
from datetime import UTC, datetime
from pathlib import Path

import pytest

from traceconomics import release, testresults
from test_release import FakeSteps, config, host, no_email  # noqa: F401 (fixtures: a fake host, no email)

URL = "https://objectstorage.example/p/SECRET/n/ns/b/traceconomics-test-results/o/"
SHA = "0123456789abcdef0123456789abcdef01234567"
STARTED = datetime(2026, 11, 10, 11, 5, 0, tzinfo=UTC)


def test_the_commit_is_read_from_git_itself(tmp_path):
    """PY-TRES-001: the build's commit is read from git's own files

    Given a repository whose HEAD points to a branch
    When the commit is read with no ref for the branch yet
    And then with the branch in packed-refs
    And then with a loose ref for it too
    And then with HEAD detached
    And from a folder with no repository
    Then without a ref there is no commit
    And with packed-refs alone, the packed commit is read
    And with a loose ref too, the loose ref wins
    And with HEAD detached, its commit is read
    And the folder with no repository has no commit
    """
    git = tmp_path / ".git"
    (git / "refs/heads").mkdir(parents=True)
    (git / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    assert testresults.source_commit(tmp_path) is None                       # no such ref yet
    (git / "packed-refs").write_text(f"# pack-refs with: peeled\n{SHA} refs/heads/main\n", encoding="utf-8")
    assert testresults.source_commit(tmp_path) == SHA                         # a packed ref
    other = "f" * 40
    (git / "refs/heads/main").write_text(other + "\n", encoding="utf-8")
    assert testresults.source_commit(tmp_path) == other                       # a loose ref wins
    (git / "HEAD").write_text(SHA + "\n", encoding="utf-8")
    assert testresults.source_commit(tmp_path) == SHA                         # detached
    assert testresults.source_commit(tmp_path / "nowhere") is None


def test_a_worktree_checkout_is_followed_to_its_repository(tmp_path):
    """PY-TRES-002: a worktree checkout is followed to its repository

    Given a worktree whose .git file points into the main repository, on a branch whose ref is kept there
    When the worktree's commit is read
    Then it is the branch's commit
    """
    main, wt = tmp_path / "main/.git", tmp_path / "main/.git/worktrees/wt"
    (main / "refs/heads").mkdir(parents=True)
    wt.mkdir(parents=True)
    (main / "refs/heads/fix").write_text(SHA + "\n", encoding="utf-8")
    (wt / "HEAD").write_text("ref: refs/heads/fix\n", encoding="utf-8")
    (wt / "commondir").write_text("../..\n", encoding="utf-8")
    (tmp_path / "wt").mkdir()
    (tmp_path / "wt/.git").write_text(f"gitdir: {wt}\n", encoding="utf-8")
    assert testresults.source_commit(tmp_path / "wt") == SHA


def test_results_then_meta_last(tmp_path):
    """PY-TRES-003: a browser step sends its results first and its meta file last

    Given a ui-test step run with a results file and a bucket link
    When its test results are sent
    Then the result is ok, with the folder named by the build, the step and the step's start time
    And the results file is sent first, as playwright.json, then meta.json
    And the meta file holds the schema version, build, commit, step, start time, environment and result
    And the environment says the data are real
    """
    results = tmp_path / "results.json"
    results.write_text('{"suites": []}', encoding="utf-8")
    sent = []
    out = testresults.send(build="20261110T110000Z", commit=SHA, step="ui-test", started=STARTED, result="passed",
                           results=results, url=URL, put=lambda u, body, t: sent.append((u, body)))
    folder = "results/20261110T110000Z/ui-test-20261110T110500Z/"
    assert out == {"result": "ok", "folder": folder}
    assert [u.removeprefix(URL) for u, _ in sent] == [folder + "playwright.json", folder + "meta.json"]
    meta = json.loads(sent[1][1])
    assert meta == {"schema": 1, "build": "20261110T110000Z", "commit": SHA, "step": "ui-test",
                    "started": "2026-11-10T11:05:00Z", "environment": testresults.environment(), "result": "passed"}
    assert meta["environment"]["data"] == "real"


def test_a_promote_check_sends_its_meta_alone():
    """PY-TRES-004: a promote check sends its meta file alone

    Given a promote check with no results file
    When its test results are sent
    Then the result is ok
    And only meta.json is sent
    """
    sent = []
    out = testresults.send(build="b", commit=SHA, step="promote", started=STARTED, result="failed", url=URL,
                           put=lambda u, body, t: sent.append(u))
    assert out["result"] == "ok" and [u.rsplit("/", 1)[1] for u in sent] == ["meta.json"]


def test_off_without_a_link_and_failures_returned_not_raised(tmp_path, monkeypatch):
    """PY-TRES-005: sending is off without a link, and failures are returned, not raised

    Given a step's test results to send
    When they are sent with no bucket link in the environment
    And with a link the bucket refuses
    And for a build whose commit is unknown
    And with a link that doesn't end in /o/, or doesn't start with https://
    And with an upload that breaks off with an error that is not an OSError
    And with an upload whose error quotes the address
    Then without a link the result is "off"
    And a refused upload is "failed", and the error doesn't repeat the link's secret
    And an unknown commit is "failed", with an error that says so
    And a wrong link is "failed", with an error saying what it should be
    And an upload that breaks off is "failed", and the error names the kind of error
    And an error that quotes the address doesn't repeat the link's secret
    """
    monkeypatch.delenv(testresults.URL_ENV, raising=False)
    assert testresults.send(build="b", commit=SHA, step="promote", started=STARTED, result="passed") == {"result": "off"}

    def refused(u, body, t):
        raise urllib.error.HTTPError(u, 401, "Unauthorized", {}, None)
    out = testresults.send(build="b", commit=SHA, step="promote", started=STARTED, result="passed", url=URL, put=refused)
    assert out["result"] == "failed" and "SECRET" not in out["error"]         # the link is never repeated
    assert testresults.send(build="b", commit=None, step="promote", started=STARTED, result="passed",
                            url=URL)["error"] == "the build's commit is unknown"
    assert "should start with https://" in testresults.send(build="b", commit=SHA, step="promote", started=STARTED,
                                                            result="passed", url=URL + "results/")["error"]
    assert "should start with https://" in testresults.send(build="b", commit=SHA, step="promote", started=STARTED,
                                                            result="passed", url=URL.replace("https://", ""))["error"]

    def torn(u, body, t):
        raise http.client.IncompleteRead(b"x")                        # not an OSError
    out = testresults.send(build="b", commit=SHA, step="promote", started=STARTED, result="passed", url=URL, put=torn)
    assert out["result"] == "failed" and out["error"].endswith("IncompleteRead: IncompleteRead")

    def quoting(u, body, t):
        raise ValueError(f"unknown url type: {u}")                     # some errors quote the address
    out = testresults.send(build="b", commit=SHA, step="promote", started=STARTED, result="passed", url=URL, put=quoting)
    assert "SECRET" not in out["error"]


class WithResults(FakeSteps):
    """The fake steps, with the browser steps writing their results file as Playwright does."""

    def __call__(self, step, env, log: Path) -> int:
        code = super().__call__(step, env, log)
        if step.name in release.BROWSER_STEPS:
            Path(env["UI_JSON"]).parent.mkdir(parents=True, exist_ok=True)
            Path(env["UI_JSON"]).write_text('{"suites": []}', encoding="utf-8")
        return code


@pytest.fixture
def uploads(monkeypatch):
    calls = []
    real = testresults.send

    def send(**kw):
        calls.append(kw)
        return real(**kw, url=URL, put=lambda u, body, t: None)
    monkeypatch.setattr(testresults, "send", send)
    return calls


def test_a_build_and_its_promote_send_every_browser_step(tmp_path, uploads, monkeypatch):
    """PY-TRES-006: a release build and its promote send every browser step

    Given a release build whose browser steps write results files, and uploads that succeed
    When the release build runs
    And the build is promoted after the repository has moved on
    Then the build records the repository's commit
    And its ui-test and smoke results are sent, both passed, with that commit
    And both uploads are recorded as ok
    And the promote check is sent as passed
    And it carries the build's commit, not the repository's new one
    And its upload is recorded as ok
    """
    cfg = config(tmp_path)
    monkeypatch.setattr(testresults, "source_commit", lambda repo: SHA)
    rec = release.build(cfg, now=datetime(2026, 11, 10, tzinfo=UTC), runner=WithResults(cfg.release.site_dir))
    assert rec["commit"] == SHA
    assert [(c["step"], c["result"], c["commit"]) for c in uploads] == [("ui-test", "passed", SHA), ("smoke", "passed", SHA)]
    assert [x["result"] for x in rec["test_results"]] == ["ok", "ok"]
    monkeypatch.setattr(testresults, "source_commit", lambda repo: "f" * 40)   # a later deploy
    done = release.promote(cfg, rec["id"], "staging", runner=FakeSteps(cfg.release.site_dir))
    assert uploads[-1]["step"] == "promote" and uploads[-1]["result"] == "passed"
    assert uploads[-1]["commit"] == SHA                                        # the build's commit, not today's
    assert done["test_results"]["result"] == "ok"


def test_a_failed_browser_step_is_sent_too_and_a_failed_upload_only_reported(tmp_path, monkeypatch, no_email):
    """PY-TRES-007: a failed browser step is sent too, and a failed upload is only reported

    Given uploads that always fail
    And a release build where ui-test fails
    When the release build runs
    And a later build's steps all pass
    Then the first build's ui-test results are sent as failed, and nothing after it
    And that build fails at ui-test, not at the upload
    And its alert email says the test results were not sent to the run history, with the step and the upload's error
    And the later build is ok despite the failed uploads
    """
    cfg = config(tmp_path)
    monkeypatch.setattr(testresults, "source_commit", lambda repo: SHA)
    calls = []

    def send(**kw):
        calls.append(kw)
        return {"result": "failed", "error": "results/x/: URLError: timed out"}
    monkeypatch.setattr(testresults, "send", send)
    rec = release.build(cfg, now=datetime(2026, 11, 10, tzinfo=UTC), runner=WithResults(cfg.release.site_dir, fail="ui-test"))
    assert [(c["step"], c["result"]) for c in calls] == [("ui-test", "failed")]
    assert rec["result"] == "failed" and rec["failed_step"] == "ui-test"      # the test failed, not the upload
    body = no_email[-1][1]
    assert "Test results not sent to the run history" in body and "ui-test: results/x/: URLError: timed out" in body

    ok = release.build(cfg, now=datetime(2026, 11, 11, tzinfo=UTC), runner=WithResults(cfg.release.site_dir))
    assert ok["result"] == "ok"                                                # a failed upload never fails a build
