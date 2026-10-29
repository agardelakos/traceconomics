"""The run heartbeat, the cloud backup (which must never include microdata), and the Linux timer."""

import json
import threading
from datetime import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from traceconomics import backup, heartbeat, schedule
from traceconomics.archive.local_only import LocalOnlyError
from traceconomics.config import Config


@pytest.fixture
def server():
    """A local stand-in for the storage service: records every PUT."""
    received = {}

    class Handler(BaseHTTPRequestHandler):
        def do_PUT(self):
            received[self.path] = self.rfile.read(int(self.headers["Content-Length"]))
            self.send_response(200)
            self.end_headers()

        def log_message(self, *args):
            pass

    httpd = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_port}/p/token/n/ns/b/bucket/o/", received
    httpd.shutdown()


def test_heartbeat_sends_counts_not_details(server):
    url, received = server
    record = {"started": "2026-11-10T11:00:02Z", "result": "ok", "stored": 3, "failures": [],
              "report": "email", "release_days": ["2026-11-10"]}
    assert heartbeat.send(record, url=url + "heartbeat.json") == "sent"
    beat = json.loads(received["/p/token/n/ns/b/bucket/o/heartbeat.json"])
    assert beat == {"started": "2026-11-10T11:00:02Z", "result": "ok", "stored": 3, "failures": 0}


def test_heartbeat_is_off_without_an_address_and_reports_failures(monkeypatch):
    monkeypatch.delenv(heartbeat.URL_ENV, raising=False)
    assert heartbeat.send({"result": "ok"}) == "off"
    assert heartbeat.send({"result": "ok"}, url="http://127.0.0.1:9/x", timeout=2).startswith("failed:")


def archive_with_microdata(root: Path) -> None:
    for rel, data in {"raw/index.jsonl": b"{}\n",
                      "raw/eurostat/prc_hicp_minr/20261110T110000Z/payload.tsv.gz": b"prices",
                      "raw/eurostat/prc_hicp_minr/20261110T110000Z/manifest.json": b"{}",
                      "raw/elstat/puf-hbs-2024/20261014T000000Z/payload.zip": b"households",
                      "raw/elstat/puf-hbs-2024/20261014T000000Z/manifest.json": b"{}",
                      "raw/elstat/puf-catalogue/20261017T000000Z/payload.html": b"<html>",
                      "outbox/report.txt": b"not archive data"}.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_bytes(data)


def test_backup_sends_the_archive_but_never_microdata(tmp_path, server):
    url, received = server
    archive_with_microdata(tmp_path)
    result = backup.sync(tmp_path, url=url)
    assert result == {"result": "ok", "sent": 4}
    sent = sorted(received)
    assert not [p for p in sent if "puf-hbs" in p]
    assert "/p/token/n/ns/b/bucket/o/raw/elstat/puf-catalogue/20261017T000000Z/payload.html" in sent
    assert not [p for p in sent if "outbox" in p]
    # Sent once: a second sync has nothing to do, until a file changes.
    assert backup.sync(tmp_path, url=url) == {"result": "ok", "sent": 0}
    (tmp_path / "raw" / "index.jsonl").write_bytes(b"{}\n{}\n")
    assert backup.sync(tmp_path, url=url) == {"result": "ok", "sent": 1}


def test_backup_guard_refuses_microdata_even_if_the_filter_misses_it(tmp_path, monkeypatch):
    archive_with_microdata(tmp_path)
    monkeypatch.setattr(backup, "is_local_only", lambda source, dataset: False)   # a broken filter
    with pytest.raises(LocalOnlyError):
        backup.plan(tmp_path)


def test_systemd_units_run_daily_in_athens_time_inside_the_pinned_image():
    cfg = Config(archive_dir=Path("/home/u/traceconomics-archive"), user_agent="t", run_after=time(13, 0))
    units = schedule.systemd_units(cfg, uid=1001, gid=1001, home=Path("/home/u"), repo=Path("/home/u/traceconomics"),
                                   venv=Path("/home/u/traceconomics-venv"), node=Path("/home/u/traceconomics-node"),
                                   env_file=Path("/home/u/.config/traceconomics/env"))
    timer = units["traceconomics-archive.timer"]
    assert "OnCalendar=*-*-* 13:00:00 Europe/Athens" in timer and "Persistent=true" in timer
    service = units["traceconomics-archive.service"]
    assert "Type=oneshot" in service
    assert f" {schedule.IMAGE} " in service and "@sha256:" in schedule.IMAGE
    assert "--user=1001:1001" in service and "--volume=/home/u:/home/u" in service
    assert "--env-file=/home/u/.config/traceconomics/env" in service
    assert service.rstrip().endswith("/home/u/traceconomics-venv/bin/python -I -m traceconomics archive")


def load_watchdog():
    import importlib.util

    path = Path(__file__).parents[1] / ".github" / "scripts" / "check_heartbeat.py"
    spec = importlib.util.spec_from_file_location("check_heartbeat", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_watchdog_rule():
    from datetime import UTC, datetime

    w = load_watchdog()
    now = datetime(2026, 11, 10, 13, 0, tzinfo=UTC)
    assert w.verdict({"started": "2026-11-10T11:00:02Z", "result": "ok"}, now) is None
    assert w.verdict({"started": "2026-11-10T10:00:02Z", "result": "not-due"}, now) is None
    # Winter time: the run is at 11:00 UTC. One missed day leaves a heartbeat 26 hours old.
    assert "26 hours" in w.verdict({"started": "2026-11-09T11:00:02Z", "result": "ok"}, now)
    assert "failures" in w.verdict({"started": "2026-11-10T11:00:02Z", "result": "failures", "failures": 2}, now)
    assert w.verdict({}, now) == "the heartbeat has no time"


def test_the_shell_command_runs_the_same_container_as_the_timer():
    where = dict(uid=1001, gid=1001, home=Path("/home/u"), repo=Path("/home/u/traceconomics"),
                 venv=Path("/home/u/traceconomics-venv"), node=Path("/home/u/traceconomics-node"),
                 env_file=Path("/home/u/.config/traceconomics/env"))
    script = schedule.shell_command(**where)
    service = schedule.systemd_units(Config(archive_dir=Path("/a"), user_agent="t"), **where)["traceconomics-archive.service"]
    assert script.startswith("#!/bin/sh\n") and "\r" not in script
    run = script.splitlines()[-1]
    assert run.startswith("exec /usr/bin/docker run ") and run.endswith(' -m traceconomics "$@"')
    # The same container, user, mounts and secrets as the timer's command, minus its "archive" argument.
    timer_run = next(l for l in service.splitlines() if l.startswith("ExecStart="))
    assert run[len("exec "):-len(' "$@"')] == timer_run[len("ExecStart="):-len(" archive")]


def test_units_and_shell_command_run_the_configured_image_else_the_pinned_one(tmp_path):
    browser = "sha256:" + "ab" * 32
    for image, expect in ((browser, browser), (None, schedule.IMAGE)):
        out = tmp_path / str(image is None)
        cfg = Config(archive_dir=Path("/a"), user_agent="t", image=image)
        schedule.write_units(cfg, out / "units", bin_dir=out / "bin", node=Path("/n"), env_file=Path("/e"))
        service = (out / "units" / "traceconomics-archive.service").read_text(encoding="utf-8")
        command = (out / "bin" / "traceconomics").read_text(encoding="utf-8")
        assert f" {expect} " in service and f" {expect} " in command
