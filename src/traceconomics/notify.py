"""One way to tell the maintainer something: email, or a file when email isn't set up.

The same function serves the laptop job and, later, a hosted scheduler; only
the settings differ. The SMTP password is never stored in the config file:
it comes from the TRACECONOMICS_SMTP_PASSWORD environment variable (for a hosted
scheduler's secrets) or from the operating system's credential store.
"""

from __future__ import annotations

import os
import re
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path

from traceconomics.archive.store import stamp, utc_now
from traceconomics.config import Config

KEYRING_SERVICE = "traceconomics-smtp"
PASSWORD_ENV = "TRACECONOMICS_SMTP_PASSWORD"


def smtp_password(username: str) -> str | None:
    if pw := os.environ.get(PASSWORD_ENV):
        return pw
    try:
        import keyring
    except ImportError:
        return None
    return keyring.get_password(KEYRING_SERVICE, username)


def notify(config: Config, subject: str, body: str) -> str:
    """Send a message. Returns where it went: "email" or the outbox file path."""
    subject = f"[Traceconomics] {subject}"
    if config.email is not None:
        try:
            _send_email(config, subject, body)
            return "email"
        except (OSError, smtplib.SMTPException, RuntimeError) as exc:
            body = f"(Email failed: {exc}. Saved here instead.)\n\n{body}"
    return str(_to_outbox(config.archive_dir / "outbox", subject, body))


def _send_email(config: Config, subject: str, body: str) -> None:
    e = config.email
    password = smtp_password(e.username)
    if not password:
        raise RuntimeError(
            f"no SMTP password: set {PASSWORD_ENV}, or store it with "
            f"`python -m keyring set {KEYRING_SERVICE} {e.username}`"
        )
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = e.sender
    msg["To"] = ", ".join(e.recipients)
    msg.set_content(body)
    context = ssl.create_default_context()
    if e.security == "ssl":
        with smtplib.SMTP_SSL(e.smtp_host, e.smtp_port, context=context, timeout=60) as s:
            s.login(e.username, password)
            s.send_message(msg)
    else:
        with smtplib.SMTP(e.smtp_host, e.smtp_port, timeout=60) as s:
            s.starttls(context=context)
            s.login(e.username, password)
            s.send_message(msg)


def _to_outbox(folder: Path, subject: str, body: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "-", subject.lower()).strip("-")[:60]
    path = folder / f"{stamp(utc_now())}-{slug}.txt"
    n = 2
    while path.exists():
        path = folder / f"{stamp(utc_now())}-{slug}-{n}.txt"
        n += 1
    path.write_text(f"Subject: {subject}\n\n{body}\n", encoding="utf-8")
    return path
