"""Release builds' test results, sent to the test-results bucket: what is sent, in which order, and
that a failure to send never stops a build or a promote. Fake uploads only: no network."""

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


def test_results_then_meta_last(tmp_path):
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
    sent = []
    out = testresults.send(build="b", commit=SHA, step="promote", started=STARTED, result="failed", url=URL,
                           put=lambda u, body, t: sent.append(u))
    assert out["result"] == "ok" and [u.rsplit("/", 1)[1] for u in sent] == ["meta.json"]


def test_off_without_a_link_and_failures_returned_not_raised(tmp_path, monkeypatch):
    monkeypatch.delenv(testresults.URL_ENV, raising=False)
    assert testresults.send(build="b", commit=SHA, step="promote", started=STARTED, result="passed") == {"result": "off"}

    def refused(u, body, t):
        raise urllib.error.HTTPError(u, 401, "Unauthorized", {}, None)
    out = testresults.send(build="b", commit=SHA, step="promote", started=STARTED, result="passed", url=URL, put=refused)
    assert out["result"] == "failed" and "SECRET" not in out["error"]         # the link is never repeated
    assert testresults.send(build="b", commit=None, step="promote", started=STARTED, result="passed",
                            url=URL)["error"] == "the build's commit is unknown"
    assert "should end in /o/" in testresults.send(build="b", commit=SHA, step="promote", started=STARTED,
                                                   result="passed", url=URL + "results/")["error"]


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
