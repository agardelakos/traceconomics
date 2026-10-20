import tomllib
import xml.etree.ElementTree as ET
from pathlib import Path

from traceconomics import schedule
from traceconomics.config import Config, parse
from traceconomics.notify import notify

TASK_NS = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}


def test_notify_without_email_writes_outbox(tmp_path):
    c = Config(archive_dir=tmp_path, user_agent="t")
    where = notify(c, "hello", "body")
    assert Path(where).read_text(encoding="utf-8").startswith("Subject: [Traceconomics] hello")


def test_task_xml_is_valid(tmp_path):
    c = Config(archive_dir=tmp_path, user_agent="t")
    xml = schedule.task_xml(c, Path("C:/venv/Scripts/pythonw.exe"))
    root = ET.fromstring(xml.split("?>", 1)[1])
    assert root.find(".//t:StartWhenAvailable", TASK_NS).text == "true"
    assert root.find(".//t:StartBoundary", TASK_NS).text.endswith("T13:00:00")
    assert root.find(".//t:Arguments", TASK_NS).text == "-I -m traceconomics archive"


def test_config_example_parses():
    example = Path(__file__).parents[1] / "config.example.toml"
    c = parse(tomllib.loads(example.read_text(encoding="utf-8")), base_dir=example.parent)
    assert c.run_after.hour == 13 and c.email is None and c.archive_dir.is_absolute()
