"""Registering the daily trigger: Windows Task Scheduler, or systemd on a Linux server.

The trigger fires every day at the configured time; the job itself decides whether a release
makes the run due. A missed trigger runs as soon as it can, e.g. after the computer was off:
"Start when available" on Windows, `Persistent=true` with systemd.

On Linux the job runs inside the official Python image, pinned by digest, so the server runs
exactly the interpreter and system libraries the tests ran on. The container runs as the user,
with the user's home folder mounted at the same path: every path in the config means the same
inside and outside, and nothing runs as root. A machine that builds releases runs an image
built on that one with a browser added (`image` in the config): the release's browser tests need
it, and every unit runs the same image, since the daily job starts releases itself.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path
from xml.sax.saxutils import escape

from traceconomics.config import Config, default_config_path

TASK_NAME = "traceconomics-archive"

# python:3.14.8-slim, multi-platform index (linux/arm64 and amd64), built 2026-10-06.
IMAGE = "python:3.14.8-slim@sha256:a2b82f3c48559aa0a8446d9af49826b6e2b2016f4cd2afabfe6013ec53729170"

SERVICE = """[Unit]
Description=Traceconomics: archive public statistics on release days, then build a release
Wants=network-online.target
After=network-online.target

[Service]
Type=oneshot
TimeoutStartSec=8h
ExecStart={command}
"""

TIMER = """[Unit]
Description=Traceconomics: daily trigger ({time} {timezone})

[Timer]
OnCalendar=*-*-* {time}:00 {timezone}
Persistent=true

[Install]
WantedBy=timers.target
"""

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
        raise SystemExit("Task Scheduler is Windows only. On Linux: `traceconomics schedule units --out "
                         "~/.config/systemd/user`, then `systemctl --user enable --now traceconomics-archive.timer`.")
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


def container_command(*, uid: int, gid: int, home: Path, repo: Path, venv: Path, node: Path,
                      env_file: Path, image: str = IMAGE, args: tuple[str, ...] = ("archive",)) -> list[str]:
    """`docker run` for one traceconomics command inside the pinned image, as the given user."""
    home, repo, venv, node, env_file = (Path(p).as_posix() for p in (home, repo, venv, node, env_file))
    path = f"{venv}/bin:{node}/bin:/usr/local/bin:/usr/bin:/bin"
    return ["/usr/bin/docker", "run", "--rm", "--init", f"--user={uid}:{gid}",
            f"--volume={home}:{home}", f"--env=HOME={home}", f"--env=PATH={path}",
            f"--env-file={env_file}", f"--workdir={repo}", image,
            f"{venv}/bin/python", "-I", "-m", "traceconomics", *args]


def systemd_units(config: Config, *, uid: int, gid: int, home: Path, repo: Path, venv: Path,
                  node: Path, env_file: Path, image: str = IMAGE) -> dict[str, str]:
    """The service and timer files, by file name."""
    cmd = container_command(uid=uid, gid=gid, home=home, repo=repo, venv=venv, node=node,
                            env_file=env_file, image=image)
    return {
        f"{TASK_NAME}.service": SERVICE.format(command=" ".join(cmd)),
        f"{TASK_NAME}.timer": TIMER.format(time=config.run_after.strftime("%H:%M"), timezone=config.timezone),
    }


def shell_command(*, uid: int, gid: int, home: Path, repo: Path, venv: Path, node: Path, env_file: Path,
                  image: str = IMAGE) -> str:
    """A `traceconomics` command for the server's shell: the same container as the timer's, so a
    command typed by hand (e.g. `traceconomics release promote <id>`) runs exactly as the job does."""
    cmd = container_command(uid=uid, gid=gid, home=home, repo=repo, venv=venv, node=node,
                            env_file=env_file, image=image, args=())
    return ("#!/bin/sh\n"
            "# Runs traceconomics in the pinned container, as the timer does. Written by\n"
            "# `traceconomics schedule units`; rewrite it there rather than editing it.\n"
            f'exec {" ".join(cmd)} "$@"\n')


def write_units(config: Config, out: Path, *, bin_dir: Path | None = None, node: Path | None = None,
                env_file: Path | None = None) -> list[Path]:
    """Write the unit files for this machine into `out` (the user's systemd folder) and the
    `traceconomics` shell command into `bin_dir` (default ~/.local/bin). Runs inside the container."""
    import os

    home = Path.home()
    where = dict(uid=os.getuid(), gid=os.getgid(), home=home, repo=Path(__file__).resolve().parents[2],
                 venv=Path(sys.prefix), node=node or home / "traceconomics-node",
                 env_file=env_file or default_config_path().with_name("env"))
    if config.image:
        where["image"] = config.image
    out.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, text in systemd_units(config, **where).items():
        (out / name).write_text(text, encoding="utf-8", newline="\n")   # Linux files, wherever written
        paths.append(out / name)
    bin_dir = bin_dir or home / ".local" / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    command = bin_dir / "traceconomics"
    command.write_text(shell_command(**where), encoding="utf-8", newline="\n")
    command.chmod(0o755)
    paths.append(command)
    return paths
