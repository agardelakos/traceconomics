"""Release builds' test results, sent to the test-results bucket: what is sent, in which order, and
that a failure to send never stops a build or a promote. Fake uploads only: no network."""

import http.client
import json
import urllib.error
from datetime import UTC, datetime
from pathlib import Path

import pytest
from test_release import FakeSteps, config, host, no_email  # noqa: F401 (fixtures: a fake host, no email)

from traceconomics import release, testresults

pytestmark = pytest.mark.unit

URL = "https://objectstorage.example/p/SECRET/n/ns/b/traceconomics-test-results/o/"
SHA = "0123456789abcdef0123456789abcdef01234567"
STARTED = datetime(2026, 11, 10, 11, 5, 0, tzinfo=UTC)


OTHER = "f" * 40


def _no_ref(git):
    pass


def _packed(git):
    (git / "packed-refs").write_text(f"# pack-refs with: peeled\n{SHA} refs/heads/main\n", encoding="utf-8")


def _loose_and_packed(git):
    _packed(git)
    (git / "refs/heads/main").write_text(OTHER + "\n", encoding="utf-8")


def _detached(git):
    _loose_and_packed(git)
    (git / "HEAD").write_text(SHA + "\n", encoding="utf-8")


@pytest.mark.parametrize(
    "layout, expected",
    [
        (_no_ref, None),
        (_packed, SHA),
        (_loose_and_packed, OTHER),
        (_detached, SHA),
    ],
    ids=["no ref", "packed only", "loose wins", "detached"],
)
def test_the_commit_is_read_from_git_itself(tmp_path, layout, expected):
    """PY-TRES-001: the build's commit is read from git's own files

    Given a repository whose HEAD points to a branch, laid out one of four ways
    When the commit is read
    Then without a ref for the branch there is no commit
    And with the branch in packed-refs alone, the packed commit is read
    And with a loose ref too, the loose ref wins
    And with HEAD detached, its commit is read
    """
    git = tmp_path / ".git"
    (git / "refs/heads").mkdir(parents=True)
    (git / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    layout(git)
    assert testresults.source_commit(tmp_path) == expected


def test_a_folder_with_no_repository_has_no_commit(tmp_path):
    """PY-TRES-008: a folder with no repository has no commit

    Given a folder with no git repository in it
    When the commit is read
    Then there is no commit
    """
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
    out = testresults.send(
        build="20261110T110000Z",
        commit=SHA,
        step="ui-test",
        started=STARTED,
        result="passed",
        results=results,
        url=URL,
        put=lambda u, body, t: sent.append((u, body)),
    )
    folder = "results/20261110T110000Z/ui-test-20261110T110500Z/"
    assert out == {"result": "ok", "folder": folder}
    assert [u.removeprefix(URL) for u, _ in sent] == [folder + "playwright.json", folder + "meta.json"]
    meta = json.loads(sent[1][1])
    assert meta == {
        "schema": 1,
        "build": "20261110T110000Z",
        "commit": SHA,
        "step": "ui-test",
        "started": "2026-11-10T11:05:00Z",
        "environment": testresults.environment(),
        "result": "passed",
    }
    assert meta["environment"]["data"] == "real"


def test_a_promote_check_sends_its_meta_alone():
    """PY-TRES-004: a promote check sends its meta file alone

    Given a promote check with no results file
    When its test results are sent
    Then the result is ok
    And only meta.json is sent
    """
    sent = []
    out = testresults.send(
        build="b",
        commit=SHA,
        step="promote",
        started=STARTED,
        result="failed",
        url=URL,
        put=lambda u, body, t: sent.append(u),
    )
    assert out["result"] == "ok" and [u.rsplit("/", 1)[1] for u in sent] == ["meta.json"]


def test_off_without_a_link(monkeypatch):
    """PY-TRES-005: sending is off without a link

    Given a step's test results to send
    When they are sent with no bucket link in the environment
    Then the result is "off"
    """
    monkeypatch.delenv(testresults.URL_ENV, raising=False)
    assert testresults.send(build="b", commit=SHA, step="promote", started=STARTED, result="passed") == {
        "result": "off"
    }


def _refused(u, body, t):
    raise urllib.error.HTTPError(u, 401, "Unauthorized", {}, None)


def _torn(u, body, t):
    raise http.client.IncompleteRead(b"x")  # not an OSError


def _quoting(u, body, t):
    raise ValueError(f"unknown url type: {u}")  # some errors quote the address


def _unused(u, body, t):
    pytest.fail("nothing is sent when the commit or the link is wrong")


@pytest.mark.parametrize(
    "commit, url, put, error",
    [
        (SHA, URL, _refused, "401"),
        (None, URL, _unused, "the build's commit is unknown"),
        (SHA, URL + "results/", _unused, "should start with https://"),
        (SHA, URL.replace("https://", ""), _unused, "should start with https://"),
        (SHA, URL, _torn, "IncompleteRead: IncompleteRead"),
        (SHA, URL, _quoting, "ValueError"),  # the type only: the message would quote the address
    ],
    ids=["refused", "unknown commit", "not ending in /o/", "not https", "broken off", "error quotes the address"],
)
def test_a_failed_send_is_returned_not_raised_and_never_repeats_the_secret(commit, url, put, error):
    """PY-TRES-009: a failed send is returned, not raised, and never repeats the link's secret

    Given a step's test results to send, with a bucket link whose path holds a secret
    And one failure: the bucket refuses, the commit is unknown, the link doesn't end in /o/ or start with https://, the upload breaks off with an error that is not an OSError, or the upload's error quotes the address
    When they are sent
    Then the result is "failed", with an error that says what went wrong
    And the error never repeats the link's secret

    The link is a pre-authenticated request: anyone holding it can write to the bucket, and errors
    end up in emails and logs.
    """
    out = testresults.send(build="b", commit=commit, step="promote", started=STARTED, result="passed", url=url, put=put)
    assert out["result"] == "failed"
    assert error in out["error"]
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
    assert [(c["step"], c["result"], c["commit"]) for c in uploads] == [
        ("ui-test", "passed", SHA),
        ("smoke", "passed", SHA),
    ]
    assert [x["result"] for x in rec["test_results"]] == ["ok", "ok"]
    monkeypatch.setattr(testresults, "source_commit", lambda repo: "f" * 40)  # a later deploy
    done = release.promote(cfg, rec["id"], "staging", runner=FakeSteps(cfg.release.site_dir))
    assert uploads[-1]["step"] == "promote" and uploads[-1]["result"] == "passed"
    assert uploads[-1]["commit"] == SHA  # the build's commit, not today's
    assert done["test_results"]["result"] == "ok"


def test_a_failed_browser_step_is_sent_too_and_a_failed_upload_only_reported(tmp_path, monkeypatch, no_email):  # noqa: F811 - the fixture imported from test_release
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
    rec = release.build(
        cfg, now=datetime(2026, 11, 10, tzinfo=UTC), runner=WithResults(cfg.release.site_dir, fail="ui-test")
    )
    assert [(c["step"], c["result"]) for c in calls] == [("ui-test", "failed")]
    assert rec["result"] == "failed" and rec["failed_step"] == "ui-test"  # the test failed, not the upload
    body = no_email[-1][1]
    assert "Test results not sent to the run history" in body and "ui-test: results/x/: URLError: timed out" in body

    ok = release.build(cfg, now=datetime(2026, 11, 11, tzinfo=UTC), runner=WithResults(cfg.release.site_dir))
    assert ok["result"] == "ok"  # a failed upload never fails a build
