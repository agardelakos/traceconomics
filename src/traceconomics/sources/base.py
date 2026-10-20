"""What every source adapter shares: a polite HTTP client and the run context.

Polite fetching means: one request at a time, a pause between requests, a
User-Agent that names the project, retries with growing waits, and respect
for each host's robots.txt.
"""

from __future__ import annotations

import email.message
import os
import time
import urllib.error
import urllib.request
import urllib.robotparser
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlsplit

from traceconomics.archive.store import Archive, StoreResult, sha256_text, utc_now

# Headers worth keeping in a manifest; the rest is noise.
KEPT_HEADERS = ("content-type", "content-length", "content-disposition", "last-modified", "etag", "date")


class FetchError(Exception):
    pass


@dataclass(frozen=True)
class Response:
    url: str
    status: int
    headers: dict[str, str]
    retrieved_at: datetime

    @property
    def filename(self) -> str | None:
        """File name from Content-Disposition, if the server sent one."""
        cd = self.headers.get("content-disposition")
        if not cd:
            return None
        msg = email.message.Message()
        msg["content-disposition"] = cd
        name = msg.get_filename()
        return os.path.basename(name) if name else None

    def manifest(self) -> dict:
        return {"status": self.status, "headers": self.headers}


class HttpClient:
    def __init__(self, user_agent: str, pause_seconds: float = 2.0, retries: int = 3, timeout: float = 120.0):
        self.user_agent = user_agent
        self.pause_seconds = pause_seconds
        self.retries = retries
        self.timeout = timeout
        self._last_request = 0.0
        self._robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}

    def download(self, url: str, dest: Path) -> Response:
        """Stream a URL to a file. Raises FetchError after the last retry."""
        self._check_robots(url)
        last_error: Exception | None = None
        for attempt in range(self.retries):
            if attempt:
                time.sleep(self.pause_seconds * 5 * attempt)
            try:
                return self._get(url, dest)
            except urllib.error.HTTPError as exc:
                last_error = exc
                if exc.code < 500 and exc.code != 429:
                    break  # a client error won't fix itself
            except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
                last_error = exc
        dest.unlink(missing_ok=True)
        raise FetchError(f"{url}: {last_error}")

    def get_bytes(self, url: str, tmp: Path) -> tuple[Response, bytes]:
        resp = self.download(url, tmp)
        try:
            return resp, tmp.read_bytes()
        finally:
            tmp.unlink(missing_ok=True)

    def _get(self, url: str, dest: Path) -> Response:
        wait = self._last_request + self.pause_seconds - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        req = urllib.request.Request(url, headers={"User-Agent": self.user_agent})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r, dest.open("wb") as f:
                while chunk := r.read(1 << 20):
                    f.write(chunk)
                f.flush()
                os.fsync(f.fileno())
                headers = {k.lower(): v for k, v in r.headers.items() if k.lower() in KEPT_HEADERS}
                return Response(url=url, status=r.status, headers=headers, retrieved_at=utc_now())
        finally:
            self._last_request = time.monotonic()

    def _check_robots(self, url: str) -> None:
        parts = urlsplit(url)
        host = f"{parts.scheme}://{parts.netloc}"
        if host not in self._robots:
            rp = urllib.robotparser.RobotFileParser()
            req = urllib.request.Request(host + "/robots.txt", headers={"User-Agent": self.user_agent})
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    rp.parse(r.read().decode("utf-8", "replace").splitlines())
            except urllib.error.HTTPError as exc:
                # No robots.txt (4xx) means no restrictions; a server error means we can't tell.
                if exc.code >= 500:
                    raise FetchError(f"{host}/robots.txt: {exc}") from exc
                rp = None
            except (urllib.error.URLError, TimeoutError) as exc:
                raise FetchError(f"{host}/robots.txt: {exc}") from exc
            self._robots[host] = rp
            self._last_request = time.monotonic()
        rp = self._robots[host]
        if rp is not None and not rp.can_fetch(self.user_agent, url):
            raise FetchError(f"{url}: disallowed by robots.txt")


@dataclass
class RunContext:
    """Everything an adapter needs for one run, plus what it reports back."""

    archive: Archive
    http: HttpClient
    today: date
    # Releases dated on or before this day are out. Before the daily run time it's yesterday,
    # so a morning run on a release day doesn't count as having fetched that release.
    released_through: date | None = None
    dry_run: bool = False
    results: list[StoreResult] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    alerts: list[str] = field(default_factory=list)
    planned: list[str] = field(default_factory=list)

    def fetch_and_store(
        self,
        source: str,
        dataset: str,
        url: str,
        *,
        ext: str | None = None,
        content_of=None,
        extra: dict | None = None,
    ) -> tuple[StoreResult | None, bytes | None]:
        """Download a URL and store it. Returns the result and, for small files, the bytes.

        content_of, if given, turns the downloaded bytes into the text used for
        change detection (e.g. the visible text of a web page).
        """
        if self.dry_run:
            self.planned.append(f"{source}/{dataset}: {url}")
            return None, None
        tmp = self.archive.new_tmp()
        try:
            resp = self.http.download(url, tmp)
        except FetchError as exc:
            self.archive.log_failure(source, dataset, url, str(exc))
            self.failures.append(f"{source}/{dataset}: {exc}")
            return None, None
        data = tmp.read_bytes() if tmp.stat().st_size <= 5_000_000 else None
        content_sha = None
        if content_of is not None and data is not None:
            content_sha = sha256_text(content_of(data))
        if ext is None:
            ext = guess_ext(resp)
        extra = dict(extra or {})
        if resp.filename:
            extra.setdefault("original_name", resp.filename)
        result = self.archive.store_file(
            source, dataset, tmp, url=url, retrieved_at=resp.retrieved_at, ext=ext,
            content_sha256=content_sha, http=resp.manifest(), extra=extra,
        )
        self.results.append(result)
        return result, data


def guess_ext(resp: Response) -> str:
    name = resp.filename
    if name and "." in name:
        return "." + name.rsplit(".", 1)[1].lower()
    ctype = resp.headers.get("content-type", "").split(";")[0].strip().lower()
    return {
        "text/html": ".html",
        "application/json": ".json",
        "application/xml": ".xml",
        "text/xml": ".xml",
        "application/pdf": ".pdf",
        "text/plain": ".txt",
        "application/gzip": ".gz",
        "application/x-gzip": ".gz",
    }.get(ctype, "")
