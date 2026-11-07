import smtplib
import subprocess
import sys
import tomllib
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path

import pytest

from traceconomics import notify as notify_mod, schedule
from traceconomics.config import Config, EmailConfig, parse
from traceconomics.notify import notify

pytestmark = pytest.mark.unit

TASK_NS = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}


def test_notify_without_email_writes_outbox(tmp_path):
    """PY-NOTIFY-001: without email settings a report goes to the outbox

    Given a configuration with no email settings
    When a report titled "hello" is sent
    Then it is written to a file in the outbox
    And the file starts with the subject line "Subject: [Traceconomics] hello"
    """
    c = Config(archive_dir=tmp_path, user_agent="t")
    where = notify(c, "hello", "body")
    assert Path(where).read_text(encoding="utf-8").startswith("Subject: [Traceconomics] hello")


def test_the_windows_task_runs_the_archive_job_daily_at_13_and_catches_up(tmp_path):
    """PY-NOTIFY-002: the Windows scheduled task runs the archive job daily at 13:00, and catches up

    Given a default configuration and a Windows Python interpreter
    When the Task Scheduler XML is written
    Then it parses as XML
    And its trigger repeats every day
    And the task starts when available if a run was missed
    And its start boundary is at 13:00
    And it runs the archive command with Python's isolated mode ("-I -m traceconomics archive")
    """
    c = Config(archive_dir=tmp_path, user_agent="t")
    xml = schedule.task_xml(c, Path("C:/venv/Scripts/pythonw.exe"))
    root = ET.fromstring(xml.split("?>", 1)[1])
    assert root.find(".//t:CalendarTrigger/t:ScheduleByDay/t:DaysInterval", TASK_NS).text == "1"
    assert root.find(".//t:StartWhenAvailable", TASK_NS).text == "true"
    assert root.find(".//t:StartBoundary", TASK_NS).text.endswith("T13:00:00")
    assert root.find(".//t:Arguments", TASK_NS).text == "-I -m traceconomics archive"


def test_config_example_parses():
    """PY-NOTIFY-003: the example configuration parses

    Given the repository's config.example.toml
    When it is parsed
    Then the run time is at hour 13
    And email is off
    And the archive folder is an absolute path
    """
    example = Path(__file__).parents[1] / "config.example.toml"
    c = parse(tomllib.loads(example.read_text(encoding="utf-8")), base_dir=example.parent)
    assert c.run_after.hour == 13 and c.email is None and c.archive_dir.is_absolute()


# -- email -------------------------------------------------------------------------------------------

class FakeSMTP:
    """Stands in for smtplib.SMTP and SMTP_SSL: records what the sender asks of the server."""
    sent: list = []

    def __init__(self, host, port, **kw):
        self.calls = [("connect", type(self).__name__, host, port, "context" in kw)]
        FakeSMTP.sent.append(self.calls)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.calls.append(("quit",))

    def starttls(self, context):
        self.calls.append(("starttls",))

    def login(self, user, password):
        if password == "wrong":
            raise smtplib.SMTPAuthenticationError(535, b"bad credentials")
        self.calls.append(("login", user, password))

    def send_message(self, msg):
        self.calls.append(("send", msg["Subject"], msg["From"], msg["To"], msg.get_content().strip()))


class FakeSMTP_SSL(FakeSMTP):
    pass


@pytest.fixture
def smtp(monkeypatch):
    FakeSMTP.sent = []
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(smtplib, "SMTP_SSL", FakeSMTP_SSL)
    monkeypatch.delenv(notify_mod.PASSWORD_ENV, raising=False)
    return FakeSMTP.sent


def _email_config(tmp_path, security="starttls"):
    return Config(archive_dir=tmp_path, user_agent="t", email=EmailConfig(
        smtp_host="smtp.example", smtp_port=587 if security == "starttls" else 465, username="bot",
        sender="Bot <bot@example>", recipients=("a@example", "b@example"), security=security))


@pytest.mark.parametrize("security, cls, tls", [("starttls", "FakeSMTP", True), ("ssl", "FakeSMTP_SSL", False)])
def test_a_report_is_emailed_with_the_configured_security(tmp_path, smtp, monkeypatch, security, cls, tls):
    """PY-NOTIFY-004: a report is emailed over STARTTLS or SSL, as configured

    Given email settings with STARTTLS on port 587, or SSL on port 465
    And the SMTP password in TRACECONOMICS_SMTP_PASSWORD
    When a report titled "run ok" is sent
    Then it goes by email
    And the connection uses the configured class and port, upgrading with STARTTLS only when configured
    And it logs in as the configured user with the password from the environment
    And the message has the project's subject prefix, the sender, both recipients and the body
    And nothing is written to the outbox
    """
    monkeypatch.setenv(notify_mod.PASSWORD_ENV, "s3cret")
    assert notify(_email_config(tmp_path, security), "run ok", "all good") == "email"
    calls = smtp[0]
    assert calls[0][:4] == ("connect", cls, "smtp.example", 587 if security == "starttls" else 465)
    assert (("starttls",) in calls) is tls
    assert ("login", "bot", "s3cret") in calls
    assert ("send", "[Traceconomics] run ok", "Bot <bot@example>", "a@example, b@example", "all good") in calls
    assert not (tmp_path / "outbox").exists()


def test_a_failed_email_falls_back_to_the_outbox_with_the_reason(tmp_path, smtp, monkeypatch):
    """PY-NOTIFY-005: a report whose email fails is saved in the outbox with the reason

    Given email settings and no SMTP password anywhere
    And, separately, a password the server refuses
    When a report is sent with each
    Then each goes to an outbox file instead of email
    And the first file says no SMTP password was found and how to store one
    And the second file names the server's refusal
    And both keep the report's subject and body
    """
    monkeypatch.setattr(notify_mod, "smtp_password", lambda user: None)
    first = Path(notify(_email_config(tmp_path), "run failed", "details"))
    text = first.read_text(encoding="utf-8")
    assert text.startswith("Subject: [Traceconomics] run failed")
    assert "(Email failed: no SMTP password: set TRACECONOMICS_SMTP_PASSWORD" in text and "keyring set" in text
    assert text.rstrip().endswith("details")
    monkeypatch.setattr(notify_mod, "smtp_password", lambda user: "wrong")
    second = Path(notify(_email_config(tmp_path), "run failed again", "details"))
    assert "bad credentials" in second.read_text(encoding="utf-8")


def test_the_smtp_password_comes_from_the_environment_then_the_keyring(monkeypatch):
    """PY-NOTIFY-006: the SMTP password comes from the environment first, then the credential store

    Given a credential store holding a password for the user "bot"
    When the password is looked up with TRACECONOMICS_SMTP_PASSWORD set
    And it is looked up without the variable
    And it is looked up with a credential store that fails
    Then the first lookup gives the variable's value
    And the second the credential store's
    And the third gives no password rather than an error

    A server may have no credential store backend at all; that is no password, not a crash.
    """
    class Store:
        def get_password(self, service, user):
            return f"{service}:{user}"

    class Broken:
        def get_password(self, service, user):
            raise RuntimeError("no backend")
    monkeypatch.setenv(notify_mod.PASSWORD_ENV, "from-env")
    monkeypatch.setitem(sys.modules, "keyring", Store())
    assert notify_mod.smtp_password("bot") == "from-env"
    monkeypatch.delenv(notify_mod.PASSWORD_ENV)
    assert notify_mod.smtp_password("bot") == "traceconomics-smtp:bot"
    monkeypatch.setitem(sys.modules, "keyring", Broken())
    assert notify_mod.smtp_password("bot") is None


def test_two_reports_in_the_same_second_get_two_outbox_files(tmp_path, monkeypatch):
    """PY-NOTIFY-007: two reports with the same subject in the same second get separate outbox files

    Given a configuration without email settings and a clock stopped at one second
    When three reports with the same subject are sent
    Then they go to three different files, the second and third numbered -2 and -3
    And each keeps its own body
    """
    monkeypatch.setattr(notify_mod, "utc_now", lambda: datetime(2026, 11, 7, 12, 0, 0, tzinfo=UTC))
    c = Config(archive_dir=tmp_path, user_agent="t")
    paths = [Path(notify(c, "same", f"body {n}")) for n in range(3)]
    assert len(set(paths)) == 3
    assert paths[1].stem.endswith("-2") and paths[2].stem.endswith("-3")
    assert [p.read_text(encoding="utf-8").strip().endswith(f"body {n}") for n, p in enumerate(paths)] == [True] * 3


# -- the Windows task ----------------------------------------------------------------------------------

@pytest.fixture
def windows(monkeypatch, tmp_path):
    """A Windows machine: sys.platform is win32 and every schtasks call is recorded, with the task
    file it was given read while it still exists."""
    calls = []

    def run(args, **kw):
        xml = Path(args[args.index("/XML") + 1]).read_text(encoding="utf-16") if "/XML" in args else None
        calls.append((args, xml, kw))
        return subprocess.CompletedProcess(args, 0, stdout="TaskName: \\traceconomics-archive\n", stderr="")
    monkeypatch.setattr(schedule.sys, "platform", "win32")
    monkeypatch.setattr(schedule.subprocess, "run", run)
    return calls


def test_the_windows_task_is_installed_removed_and_shown_with_schtasks(tmp_path, windows, monkeypatch):
    """PY-SCHED-008: the Windows task is installed, removed and shown with schtasks

    Given a Windows machine whose Python has a windowless pythonw.exe beside it
    When the task is installed, then shown, then removed
    Then install creates the task "traceconomics-archive" from an XML file, replacing any old one, and returns its name
    And the task runs the windowless interpreter
    And show prints schtasks' verbose listing of the task
    And remove deletes the task without asking
    """
    exe = tmp_path / "python.exe"
    exe.write_bytes(b"")
    (tmp_path / "pythonw.exe").write_bytes(b"")
    monkeypatch.setattr(schedule.sys, "executable", str(exe))
    c = Config(archive_dir=tmp_path, user_agent="t")
    assert schedule.install(c) == "traceconomics-archive"
    args, xml, kw = windows[0]
    assert args[:3] == ["schtasks", "/Create", "/TN"] and args[3] == "traceconomics-archive" and args[-1] == "/F"
    assert kw.get("check") is True and f"<Command>{tmp_path / 'pythonw.exe'}</Command>" in xml
    assert schedule.show() == "TaskName: \\traceconomics-archive\n"
    assert windows[1][0] == ["schtasks", "/Query", "/TN", "traceconomics-archive", "/V", "/FO", "LIST"]
    schedule.remove()
    assert windows[2][0] == ["schtasks", "/Delete", "/TN", "traceconomics-archive", "/F"]


def test_without_pythonw_the_task_runs_the_current_interpreter(tmp_path, monkeypatch):
    """PY-SCHED-009: without pythonw.exe the task runs the current interpreter

    Given a Python with no pythonw.exe beside it
    When the interpreter for the task is chosen
    Then it is the current interpreter
    """
    exe = tmp_path / "python.exe"
    monkeypatch.setattr(schedule.sys, "executable", str(exe))
    assert schedule._pythonw() == exe
