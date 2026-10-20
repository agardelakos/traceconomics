"""User settings, read from a TOML file kept outside the repository.

The file holds local paths and an email address, so it is never committed.
`config.example.toml` in the repository root lists every field.
"""

from __future__ import annotations

import os
import sys
import tomllib
from dataclasses import dataclass, field
from datetime import date, time
from pathlib import Path

CONFIG_ENV = "TRACECONOMICS_CONFIG"


def default_config_path() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "traceconomics" / "config.toml"


@dataclass(frozen=True)
class EmailConfig:
    smtp_host: str
    smtp_port: int
    username: str
    sender: str
    recipients: tuple[str, ...]
    # "starttls" (usually port 587) or "ssl" (usually port 465).
    security: str = "starttls"


@dataclass(frozen=True)
class ReleaseConfig:
    """Building releases after the archive job (`traceconomics release`). Off unless enabled:
    only the machine that publishes the site builds releases."""

    enabled: bool = False
    # Each build keeps its outputs, site files and report here.
    releases_dir: Path = field(default_factory=lambda: Path.home() / "traceconomics-releases")
    # The website project (the repository's site/ folder) and its name on the host.
    site_dir: Path | None = None
    worker_name: str = "traceconomics"
    # Where promoting a build puts it: a private preview alias until launch, then "production".
    promote_to: str = "staging"
    # Builds kept on disk, newest first; the promoted one is always kept.
    keep: int = 12
    replicates: int = 1000


@dataclass(frozen=True)
class Config:
    archive_dir: Path
    user_agent: str
    timezone: str = "Europe/Athens"
    # Both ELSTAT and Eurostat publish at 12:00 Greek time; the job waits an hour.
    run_after: time = time(13, 0)
    request_pause_seconds: float = 2.0
    email: EmailConfig | None = None
    # Release dates added by hand, for when a published calendar can't be read.
    extra_release_dates: tuple[date, ...] = field(default_factory=tuple)
    # The observation store: a cache rebuilt from the archive, so it needs no backup.
    store_dir: Path = field(default_factory=lambda: Path.home() / "traceconomics-store")
    store_memory_limit: str = "2GB"
    store_threads: int | None = None
    release: ReleaseConfig = field(default_factory=ReleaseConfig)


class ConfigError(Exception):
    pass


def load(path: Path | None = None) -> Config:
    path = path or Path(os.environ.get(CONFIG_ENV) or default_config_path())
    if not path.is_file():
        raise ConfigError(
            f"No config file at {path}. Copy config.example.toml there and edit it, "
            f"or point {CONFIG_ENV} at your file."
        )
    with path.open("rb") as f:
        raw = tomllib.load(f)
    return parse(raw, base_dir=path.parent)


def _path(text: str, base_dir: Path) -> Path:
    p = Path(os.path.expandvars(os.path.expanduser(text)))
    return p if p.is_absolute() else base_dir / p


def parse(raw: dict, base_dir: Path) -> Config:
    try:
        archive = raw["archive"]
        fetch = raw.get("fetch", {})
        schedule = raw.get("schedule", {})
        archive_dir = _path(archive["dir"], base_dir)
        store = raw.get("store", {})
        email = None
        if "email" in raw:
            e = raw["email"]
            email = EmailConfig(
                smtp_host=e["smtp_host"],
                smtp_port=int(e["smtp_port"]),
                username=e["username"],
                sender=e.get("sender", e["username"]),
                recipients=tuple(e["recipients"]),
                security=e.get("security", "starttls"),
            )
            if email.security not in ("starttls", "ssl"):
                raise ConfigError("email.security must be 'starttls' or 'ssl'")
        rel = raw.get("release", {})
        release = ReleaseConfig(
            enabled=bool(rel.get("enabled", False)),
            releases_dir=_path(rel.get("dir", "~/traceconomics-releases"), base_dir),
            site_dir=_path(rel["site_dir"], base_dir) if "site_dir" in rel else None,
            worker_name=str(rel.get("worker_name", "traceconomics")),
            promote_to=str(rel.get("promote_to", "staging")),
            keep=int(rel.get("keep", 12)),
            replicates=int(rel.get("replicates", 1000)),
        )
        if release.enabled and release.site_dir is None:
            raise ConfigError("release.site_dir is required when release.enabled is true")
        run_after = schedule.get("run_after", "13:00")
        hour, minute = (int(x) for x in run_after.split(":"))
        return Config(
            archive_dir=archive_dir,
            user_agent=fetch["user_agent"],
            timezone=schedule.get("timezone", "Europe/Athens"),
            run_after=time(hour, minute),
            request_pause_seconds=float(fetch.get("pause_seconds", 2.0)),
            email=email,
            extra_release_dates=tuple(
                date.fromisoformat(d) for d in schedule.get("extra_release_dates", [])
            ),
            store_dir=_path(store.get("dir", "~/traceconomics-store"), base_dir),
            store_memory_limit=str(store.get("memory_limit", "2GB")),
            store_threads=int(store["threads"]) if "threads" in store else None,
            release=release,
        )
    except KeyError as exc:
        raise ConfigError(f"Missing config field: {exc}") from exc
