"""Registering the daily trigger with Windows Task Scheduler.

The task fires every day at the configured time; the job itself decides
whether a release makes the run due. "Start when available" makes Windows run
a missed trigger as soon as it can, e.g. after the computer was off.
After moving to a hosted scheduler this module is no longer needed.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path
from xml.sax.saxutils import escape

from traceconomics.config import Config

TASK_NAME = "traceconomics-archive"

TEMPLATE = """<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>Traceconomics: archive public statistics on release days</Description>
  </RegistrationInfo>
  <Triggers>
    <CalendarTrigger>
      <StartBoundary>{start}</StartBoundary>
      <Enabled>true</Enabled>
      <ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay>
    </CalendarTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <ExecutionTimeLimit>PT2H</ExecutionTimeLimit>
    <Enabled>true</Enabled>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{command}</Command>
      <Arguments>{arguments}</Arguments>
    </Exec>
  </Actions>
</Task>
"""


def task_xml(config: Config, python: Path) -> str:
    start = f"{date.today().isoformat()}T{config.run_after.strftime('%H:%M')}:00"
    return TEMPLATE.format(
        start=start,
        command=escape(str(python)),
        arguments=escape("-I -m traceconomics archive"),
    )


def _pythonw() -> Path:
    """The windowless interpreter next to the current one, so no console flashes up."""
    exe = Path(sys.executable)
    w = exe.with_name("pythonw.exe")
    return w if w.is_file() else exe


def install(config: Config) -> str:
    if sys.platform != "win32":
        raise SystemExit("Task Scheduler is Windows only; use cron or a hosted scheduler elsewhere.")
    xml = task_xml(config, _pythonw())
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "task.xml"
        path.write_text(xml, encoding="utf-16")
        subprocess.run(["schtasks", "/Create", "/TN", TASK_NAME, "/XML", str(path), "/F"], check=True)
    return TASK_NAME


def remove() -> None:
    subprocess.run(["schtasks", "/Delete", "/TN", TASK_NAME, "/F"], check=True)


def show() -> str:
    out = subprocess.run(["schtasks", "/Query", "/TN", TASK_NAME, "/V", "/FO", "LIST"],
                         capture_output=True, text=True)
    return out.stdout or out.stderr
