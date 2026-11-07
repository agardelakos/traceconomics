import tomllib
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from traceconomics import schedule
from traceconomics.config import Config, parse
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
