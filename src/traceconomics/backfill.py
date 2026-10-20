"""Adding files that weren't fetched by the job: manual downloads and earlier copies.

`import_file` adds one file downloaded by hand, such as microdata that need a
login. `seed` copies earlier downloads into the archive, but only those whose
source and date are recorded next to them:
- a MANIFEST.md table (file, URL, date, SHA-256), or a README table plus a
  SHA256SUMS file; the checksum is verified first;
- an ELSTAT file saved as `{documentID}__{name}` with its HTTP response
  headers in `{documentID}.hdr`; the URL is rebuilt from the document ID, the
  date comes from the response's Date header, and the size must match its
  Content-Length.
Files are copied, never moved or unpacked.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from email.utils import parsedate_to_datetime

from traceconomics.archive.store import Archive, StoreResult, sha256_file, utc_now
from traceconomics.sources import elstat
from traceconomics.sources.base import KEPT_HEADERS

DATA_HOSTS = ("statistics.gr", "ec.europa.eu")
SEED_NOTE = "copied from an earlier research download; only the download date is known"


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:80] or "file"


def dataset_for_url(url: str) -> tuple[str, str] | None:
    """(source, dataset) for a URL we archive, or None for other publishers."""
    parts = urlsplit(url)
    host = parts.netloc.split(":")[0].lower()
    if host.endswith("statistics.gr"):
        m = re.search(r"documentID=(\d+)", url)
        if m:
            loc = re.search(r"locale=([a-z]{2})", url)
            lang = loc.group(1) if loc else "en"
            return "elstat", f"doc-{m.group(1)}" + ("" if lang == "en" else f"-{lang}")
        return "elstat", slug(parts.path)
    if host == "ec.europa.eu" and parts.path.startswith("/eurostat"):
        if "/api/dissemination/" in parts.path and "/data/" in parts.path:
            after = parts.path.split("/data/", 1)[1].strip("/").split("/")
            query = parse_qs(parts.query)
            filters = {k for k in query if k not in ("format", "compressed", "lang")}
            partial = (len(after) > 1 and after[1]) or filters
            code, fmt = after[0].lower(), slug(query.get("format", ["json"])[0])
            if not partial and fmt == "tsv":
                return "eurostat", code  # the same file the job downloads
            # Other formats and partial extracts are kept apart from the job's full snapshots.
            return "eurostat", f"{code}-{'extract' if partial else 'full'}-{fmt}"
        m = re.search(r"/dataflow/ESTAT/([A-Za-z0-9_]+)/", parts.path)
        if m:
            return "eurostat", f"{m.group(1).lower()}-dataflow"
        return "eurostat", slug(parts.path.removeprefix("/eurostat"))
    return None


def import_file(archive: Archive, path: Path, *, source: str, dataset: str | None, url: str | None,
                downloaded: date | None, note: str | None) -> StoreResult:
    dataset = dataset or f"puf-{slug(path.stem)}"
    when = datetime.combine(downloaded, datetime.min.time(), UTC) if downloaded else utc_now()
    extra = {"original_name": path.name, "note": note or "downloaded by hand"}
    if downloaded:
        extra["retrieved_at_precision"] = "date"
    return archive.store_file(source, dataset, path, url=url, retrieved_at=when, ext=_ext(path),
                              kind="manual", dedupe="any", extra=extra, move=False)


# -- seeding ----------------------------------------------------------------

@dataclass
class Candidate:
    path: Path
    url: str | None
    day: date
    sha256: str | None
    source: str
    dataset: str
    kind: str = "seeded"
    http: dict | None = None
    when: datetime | None = None


@dataclass
class SeedReport:
    stored: list[str] = field(default_factory=list)
    unchanged: int = 0
    skipped: list[str] = field(default_factory=list)
    bad_checksum: list[str] = field(default_factory=list)
    unrecorded: int = 0  # files with no recorded URL, so not seeded


def _ext(path: Path) -> str:
    name = path.name.lower()
    for double in (".tsv.gz", ".csv.gz", ".sdmx.zip"):
        if name.endswith(double):
            return double
    return path.suffix.lower()


def _cell(s: str) -> str:
    return s.strip().strip("`").strip()


def _md_tables(text: str) -> list[list[dict[str, str]]]:
    """Markdown tables as lists of {lower-case header: cell}."""
    tables, rows, header = [], [], None
    for line in text.splitlines() + [""]:
        if line.startswith("|"):
            cells = [_cell(c) for c in line.strip().strip("|").split("|")]
            if header is None:
                header = [c.lower() for c in cells]
            elif not all(set(c) <= set("-: ") for c in cells):
                rows.append(dict(zip(header, cells)))
        elif header is not None:
            tables.append(rows)
            rows, header = [], None
    return tables


def _pick(row: dict[str, str], *names: str) -> str | None:
    for key, value in row.items():
        if any(n in key for n in names):
            return value
    return None


def _sha256sums(folder: Path) -> dict[str, str]:
    path = folder / "SHA256SUMS"
    if not path.is_file():
        return {}
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.split(maxsplit=1)
        if len(parts) == 2:
            out[parts[1].lstrip("*").strip()] = parts[0].lower()
    return out


def _folder_date(folder: Path) -> date | None:
    for part in reversed(folder.parts):
        m = re.search(r"(\d{4}-\d{2}-\d{2})$", part)
        if m:
            return date.fromisoformat(m.group(1))
    return None


def find_candidates(research_root: Path) -> tuple[list[Candidate], list[str], int]:
    """Seedable files, files listed but unusable, and the number of files nothing records."""
    candidates: list[Candidate] = []
    skipped: list[str] = []
    listed: set[Path] = set()
    for doc in sorted(research_root.rglob("*.md")):
        if doc.name not in ("MANIFEST.md", "README.md"):
            continue
        folder = doc.parent
        sums = _sha256sums(folder)
        for table in _md_tables(doc.read_text(encoding="utf-8", errors="replace")):
            for row in table:
                name, url = _pick(row, "file"), _pick(row, "url", "source")
                if not name or not url or not url.startswith("http"):
                    continue
                day_text = _pick(row, "date", "downloaded")
                day = date.fromisoformat(day_text[:10]) if day_text and re.match(r"\d{4}-\d{2}-\d{2}", day_text) else _folder_date(folder)
                sha = _pick(row, "sha")
                sha = sha.lower() if sha and re.fullmatch(r"[0-9a-fA-F]{64}", sha) else sums.get(name)
                path = folder / name
                listed.add(path.resolve())
                where = dataset_for_url(url)
                if where is None:
                    continue  # papers and other publishers' files aren't part of the data archive
                if not path.is_file() or day is None or sha is None:
                    skipped.append(f"{path}: missing file, date or checksum")
                    continue
                candidates.append(Candidate(path, url, day, sha, *where))
    # Microdata downloaded by hand: a SHA256SUMS file, no URL (they need a login).
    for sums_file in sorted(research_root.rglob("elstat-puf/*/archives/SHA256SUMS")):
        for name, sha in _sha256sums(sums_file.parent).items():
            path = sums_file.parent / name
            if path.is_file():
                day = datetime.fromtimestamp(path.stat().st_mtime, UTC).date()
                candidates.append(Candidate(path, None, day, sha, "elstat", f"puf-{slug(path.stem)}", kind="manual"))
                listed.add(path.resolve())
    for c in _hdr_candidates(research_root, listed):
        candidates.append(c)
        listed.add(c.path.resolve())
    records = {"MANIFEST.md", "README.md", "SHA256SUMS"}
    unrecorded = sum(
        1 for p in research_root.rglob("*")
        if p.is_file() and p.name not in records and p.suffix != ".hdr" and p.resolve() not in listed
    )
    return candidates, skipped, unrecorded


def _read_hdr(path: Path) -> tuple[int, dict[str, str]]:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    status = int(lines[0].split()[1]) if lines and lines[0].startswith("HTTP/") else 0
    headers = {}
    for line in lines[1:]:
        if ":" in line:
            k, v = line.split(":", 1)
            if k.strip().lower() in KEPT_HEADERS:
                headers[k.strip().lower()] = v.strip()
    return status, headers


def _hdr_candidates(research_root: Path, listed: set[Path]) -> list[Candidate]:
    out = []
    for hdr in sorted(research_root.rglob("*.hdr")):
        doc = hdr.stem
        if not doc.isdigit():
            continue
        files = [p for p in hdr.parent.glob(f"{doc}__*") if p.is_file()]
        if len(files) != 1 or files[0].resolve() in listed:
            continue
        path = files[0]
        status, headers = _read_hdr(hdr)
        if status != 200 or "date" not in headers:
            continue
        if "content-length" in headers and int(headers["content-length"]) != path.stat().st_size:
            continue
        lang = "el" if hdr.parent.name.endswith("_el") or "_GR." in path.name else "en"
        url = elstat.DOC_URL.format(doc=doc).replace("locale=en", f"locale={lang}")
        when = parsedate_to_datetime(headers["date"]).astimezone(UTC)
        dataset = f"doc-{doc}" + ("" if lang == "en" else "-el")
        out.append(Candidate(path, url, when.date(), None, "elstat", dataset,
                             http={"status": status, "headers": headers}, when=when))
    return out


def seed(archive: Archive, research_root: Path, *, dry_run: bool = False) -> SeedReport:
    report = SeedReport()
    candidates, report.skipped, report.unrecorded = find_candidates(research_root)
    seen: set[Path] = set()
    for c in sorted(candidates, key=lambda c: (c.day, str(c.path))):
        if c.path in seen:
            continue
        seen.add(c.path)
        if dry_run:
            report.stored.append(f"{c.source}/{c.dataset} <- {c.path.name} ({c.day})")
            continue
        if c.sha256 is not None and sha256_file(c.path) != c.sha256:
            report.bad_checksum.append(str(c.path))
            continue
        extra = {"original_name": c.path.name, "note": SEED_NOTE, "published_at_quality": "first_seen"}
        if c.http is None:
            extra["retrieved_at_precision"] = "date"
            when = datetime.combine(c.day, datetime.min.time(), UTC)
        else:
            extra["note"] = "copied from an earlier research download; URL rebuilt from the document ID"
            when = c.when
        result = archive.store_file(
            c.source, c.dataset, c.path, url=c.url, retrieved_at=when, http=c.http,
            ext=_ext(c.path), kind=c.kind, dedupe="any", extra=extra, move=False,
        )
        if result.status == "stored":
            report.stored.append(f"{c.source}/{c.dataset}")
        else:
            report.unchanged += 1
    return report
