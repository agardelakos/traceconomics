"""One-off: move a local setup from the project's earlier name (open-econ-tracker, package `oet`)
to Traceconomics.

What moves:
- the config file: a new one is written under the new name, with the folder paths, User-Agent
  and comments updated; the old file is left as it was;
- the archive, store and outputs folders: renamed in place (same drive, so nothing is copied
  and nothing is deleted), and only when the new name isn't taken;
- the mailbox password in the system keyring: copied to the new service name, never shown; the
  old entry is left;
- the scheduled task: the old one is removed (its command names the old package); install the
  new one with `traceconomics schedule install` once the code is in its final folder.

What stays: the archive's own records, including the "oet-local" label of datasets built
locally, since archived data is never rewritten.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

OLD_CONFIG_DIR, NEW_CONFIG_DIR = "oet", "traceconomics"
OLD_KEYRING, NEW_KEYRING = "oet-smtp", "traceconomics-smtp"
OLD_TASK = "oet-archive"
FOLDERS = ("archive", "store", "outputs")

CONFIG_RULES = [
    (re.compile(r"(?<![\w-])oet-(archive|store|outputs)\b"), r"traceconomics-\1"),
    (re.compile(r"open-econ-tracker/0\.1"), "Traceconomics/0.1"),
    (re.compile(r"open-econ-tracker"), "Traceconomics"),
    (re.compile(r"%APPDATA%\\oet\\"), r"%APPDATA%\\traceconomics\\"),
    (re.compile(r"~/\.config/oet/"), "~/.config/traceconomics/"),
    (re.compile(r"\bOET_CONFIG\b"), "TRACECONOMICS_CONFIG"),
    (re.compile(r"\bOET_SMTP_PASSWORD\b"), "TRACECONOMICS_SMTP_PASSWORD"),
    (re.compile(r"\boet-smtp\b"), "traceconomics-smtp"),
]


def _config_base() -> Path:
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))


def rewrite_config(text: str) -> str:
    for pattern, replacement in CONFIG_RULES:
        text = pattern.sub(replacement, text)
    return text


@dataclass
class Plan:
    steps: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)


def _username(config_text: str) -> str | None:
    m = re.search(r'^\s*username\s*=\s*"([^"]+)"', config_text, re.MULTILINE)
    return m.group(1) if m else None


def run(dry_run: bool = True, home: Path | None = None, config_base: Path | None = None,
        keyring_module=None, schtasks=True) -> Plan:
    home = home or Path.home()
    base = config_base or _config_base()
    plan = Plan()
    old_cfg, new_cfg = base / OLD_CONFIG_DIR / "config.toml", base / NEW_CONFIG_DIR / "config.toml"

    old_text = old_cfg.read_text(encoding="utf-8") if old_cfg.exists() else None
    if old_text is None:
        plan.steps.append(f"config: no old config at {old_cfg}; nothing to move")
    elif new_cfg.exists():
        plan.steps.append(f"config: {new_cfg} exists already; left as it is")
    else:
        plan.steps.append(f"config: write {new_cfg} (paths, User-Agent and comments renamed); keep {old_cfg}")
        if not dry_run:
            new_cfg.parent.mkdir(parents=True, exist_ok=True)
            new_cfg.write_text(rewrite_config(old_text), encoding="utf-8")

    for name in FOLDERS:
        old, new = home / f"oet-{name}", home / f"traceconomics-{name}"
        if not old.exists():
            plan.steps.append(f"folder: {old} not found; nothing to move")
        elif new.exists():
            plan.problems.append(f"folder: both {old} and {new} exist; not moved (merge them by hand)")
        else:
            plan.steps.append(f"folder: rename {old} -> {new}")
            if not dry_run:
                os.rename(old, new)          # same drive: a rename, never a copy and delete

    user = _username(old_text) if old_text else None
    if user:
        kr = keyring_module
        if kr is None:
            import keyring as kr
        secret = kr.get_password(OLD_KEYRING, user)
        if secret is None:
            plan.steps.append(f"keyring: no password under {OLD_KEYRING}; set one with "
                              f"`python -m keyring set {NEW_KEYRING} <username>`")
        elif kr.get_password(NEW_KEYRING, user) is not None:
            plan.steps.append(f"keyring: {NEW_KEYRING} already has a password; left as it is")
        else:
            plan.steps.append(f"keyring: copy the mailbox password from {OLD_KEYRING} to {NEW_KEYRING} (not shown)")
            if not dry_run:
                kr.set_password(NEW_KEYRING, user, secret)

    if schtasks and sys.platform == "win32":
        exists = subprocess.run(["schtasks", "/Query", "/TN", OLD_TASK], capture_output=True).returncode == 0
        if exists:
            plan.steps.append(f"task: remove the old scheduled task {OLD_TASK} (install the new one with "
                              "`traceconomics schedule install` after the repository folder is renamed)")
            if not dry_run:
                subprocess.run(["schtasks", "/Delete", "/TN", OLD_TASK, "/F"], check=True, capture_output=True)
        else:
            plan.steps.append(f"task: no scheduled task {OLD_TASK}")
    return plan
