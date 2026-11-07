import hashlib
from datetime import date

import pytest

from traceconomics.archive.store import Archive
from traceconomics.backfill import dataset_for_url, import_file, seed

pytestmark = pytest.mark.integration

ELSTAT_DOC = "https://www.statistics.gr/en/statistics?_documentID={}&_locale=en"
EUROSTAT_DATA = "https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/data/"


def _sha(b):
    return hashlib.sha256(b).hexdigest()


def test_dataset_for_url():
    """PY-BACKFILL-001: a source URL names its archive dataset

    Given ELSTAT document URLs in English and Greek, Eurostat full TSV, full SDMX-CSV and partial-extract URLs, and another publisher's URL
    When the dataset for each URL is worked out
    Then an ELSTAT document is ("elstat", "doc-<id>"), with "-el" added for the Greek locale
    And a full Eurostat TSV is ("eurostat", "<code>"), the same dataset the job downloads
    And a full SDMX-CSV is "<code>-full-sdmx-csv" and a partial extract "<code>-extract-sdmx-csv"
    And another publisher's URL gives None
    """
    assert dataset_for_url("https://www.statistics.gr:443/en/statistics?x=1&_documentID=585819&_locale=en") == ("elstat", "doc-585819")
    assert dataset_for_url("https://www.statistics.gr/el/statistics?_documentID=114834&_locale=el") == ("elstat", "doc-114834-el")
    assert dataset_for_url(EUROSTAT_DATA + "prc_hicp_fp?format=TSV&compressed=true") == ("eurostat", "prc_hicp_fp")
    assert dataset_for_url(EUROSTAT_DATA + "prc_hicp_fp?format=SDMX-CSV&compressed=true") == ("eurostat", "prc_hicp_fp-full-sdmx-csv")
    assert dataset_for_url(EUROSTAT_DATA + "prc_hicp_manr/M.RCH_A.CP00.EL/?format=SDMX-CSV")[1] == "prc_hicp_manr-extract-sdmx-csv"
    assert dataset_for_url("https://www.bankofgreece.gr/paper.pdf") is None


def test_seed_copies_verified_files_only(tmp_path):
    """PY-BACKFILL-002: seeding copies only files whose checksum matches the manifest

    Given a research folder whose MANIFEST.md lists a matching ELSTAT file, a changed ELSTAT file and a file from another publisher
    When the archive is seeded from it
    And it is seeded again
    Then only the matching file is stored, as elstat/doc-1
    And exactly one file is reported with a bad checksum
    And the research file is still in place (copied, not moved)
    And the snapshot is of kind "seeded", retrieved at the manifest's download date at midnight UTC
    And the second seeding reports one file unchanged
    """
    research = tmp_path / "research" / "elstat" / "pass-2026-10-17"
    research.mkdir(parents=True)
    (research / "good.xlsx").write_bytes(b"good")
    (research / "bad.xlsx").write_bytes(b"tampered")
    (research / "paper.pdf").write_bytes(b"paper")
    (research / "MANIFEST.md").write_text(
        "| File | Source URL | Downloaded | SHA-256 | What it is |\n|---|---|---|---|---|\n"
        f"| `good.xlsx` | {ELSTAT_DOC.format(1)} | 2026-10-17 | `{_sha(b'good')}` | ok |\n"
        f"| bad.xlsx | {ELSTAT_DOC.format(2)} | 2026-10-17 | {_sha(b'original')} | changed since |\n"
        f"| paper.pdf | https://example.org/paper.pdf | 2026-10-17 | {_sha(b'paper')} | not data |\n",
        encoding="utf-8",
    )
    archive = Archive(tmp_path / "archive")
    rep = seed(archive, tmp_path / "research")
    assert rep.stored == ["elstat/doc-1"]
    assert len(rep.bad_checksum) == 1
    assert (research / "good.xlsx").exists()  # copied, not moved
    snap = archive.latest("elstat", "doc-1")
    assert snap["retrieved_at"] == "2026-10-17T00:00:00Z" and snap["kind"] == "seeded"
    assert seed(archive, tmp_path / "research").unchanged == 1  # running it again changes nothing


def test_seed_uses_sha256sums_and_folder_date(tmp_path):
    """PY-BACKFILL-003: seeding reads SHA256SUMS and takes the date from the folder name

    Given a folder named for a date holding a Eurostat file, its SHA256SUMS line and a README table with its source URL
    When the archive is seeded from it
    Then the file is stored as eurostat/prc_hicp_fp
    And its snapshot is retrieved on the folder's date
    """
    folder = tmp_path / "research" / "archive" / "prc_hicp_fp" / "2026-10-14"
    folder.mkdir(parents=True)
    (folder / "prc_hicp_fp.tsv.gz").write_bytes(b"gz")
    (folder / "SHA256SUMS").write_text(f"{_sha(b'gz')} *prc_hicp_fp.tsv.gz\n", encoding="utf-8")
    (folder / "README.md").write_text(
        "| File | Source URL |\n|---|---|\n"
        f"| `prc_hicp_fp.tsv.gz` | {EUROSTAT_DATA}prc_hicp_fp?format=TSV&compressed=true |\n",
        encoding="utf-8",
    )
    archive = Archive(tmp_path / "archive")
    assert seed(archive, tmp_path / "research").stored == ["eurostat/prc_hicp_fp"]
    assert archive.latest("eurostat", "prc_hicp_fp")["retrieved_at"].startswith("2026-10-14")


def test_import_manual_download(tmp_path):
    """PY-BACKFILL-004: a hand-downloaded file is imported as a manual snapshot

    Given a file downloaded by hand, with no dataset or URL given
    When it is imported for ELSTAT with its download date
    Then it is stored under the dataset "puf-" plus the file's name in slug form
    And the original file is left in place
    And its manifest says kind "manual"
    """
    f = tmp_path / "HBS_2025.zip"
    f.write_bytes(b"zip")
    archive = Archive(tmp_path / "archive")
    r = import_file(archive, f, source="elstat", dataset=None, url=None, downloaded=date(2026, 4, 2), note=None)
    assert r.status == "stored" and r.dataset == "puf-hbs-2025" and f.exists()
    assert archive.manifest(archive.latest("elstat", "puf-hbs-2025"))["kind"] == "manual"


def test_other_pages_of_the_publishers_get_their_own_datasets():
    """PY-BACKFILL-005: publishers' pages that aren't data files get datasets named after their paths

    Given an ELSTAT page without a document ID, a Eurostat dataflow definition and another Eurostat page
    When the dataset for each URL is worked out
    Then the ELSTAT page is named by its path in slug form
    And the dataflow is "<code>-dataflow"
    And the other Eurostat page is named by its path in slug form, without "/eurostat"
    """
    assert dataset_for_url("https://www.statistics.gr/en/statistics/-/publication/DKT87") == \
        ("elstat", "en-statistics-publication-dkt87")
    assert dataset_for_url("https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/dataflow/ESTAT/PRC_HICP_MINR/1.0") == \
        ("eurostat", "prc_hicp_minr-dataflow")
    assert dataset_for_url("https://ec.europa.eu/eurostat/web/hicp/database") == ("eurostat", "web-hicp-database")


def _hdr(folder, doc, name, body, *, status=200, length=None, date_line=True):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{doc}__{name}").write_bytes(body)
    lines = [f"HTTP/1.1 {status} OK", f"Content-Length: {len(body) if length is None else length}",
             "Content-Type: application/vnd.ms-excel", "Set-Cookie: session=1"]
    if date_line:
        lines.append("Date: Tue, 14 Oct 2026 10:30:00 GMT")
    (folder / f"{doc}.hdr").write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_seed_takes_elstat_files_saved_with_their_response_headers(tmp_path):
    """PY-BACKFILL-006: seeding takes ELSTAT files saved with their HTTP response headers

    Given a research folder "downloads_el" holding "585819__Table_GR.xls" and its 585819.hdr: status 200, a Date, a matching length and a cookie
    And files whose .hdr says 404, has no Date, gives another length, or is not named by a document ID
    And a document ID with two saved files
    When the archive is seeded from it
    Then only document 585819 is stored, as the Greek dataset elstat/doc-585819-el
    And its snapshot is retrieved at the Date header's time and its URL asks for the Greek page
    And its manifest keeps the content type and length, not the cookie
    And the files whose headers don't vouch for them are left out
    And the .hdr files themselves are never counted as unrecorded files
    """
    folder = tmp_path / "research" / "downloads_el"
    _hdr(folder, "585819", "Table_GR.xls", b"table")
    _hdr(folder, "1", "a.xls", b"a", status=404)
    _hdr(folder, "2", "b.xls", b"b", date_line=False)
    _hdr(folder, "3", "c.xls", b"c", length=99)
    _hdr(folder, "notes", "d.xls", b"d")
    _hdr(folder, "4", "e.xls", b"e")
    (folder / "4__e-copy.xls").write_bytes(b"e2")
    archive = Archive(tmp_path / "archive")
    rep = seed(archive, tmp_path / "research")
    assert rep.stored == ["elstat/doc-585819-el"]
    snap = archive.latest("elstat", "doc-585819-el")
    assert snap["retrieved_at"] == "2026-10-14T10:30:00Z"
    m = archive.manifest(snap)
    assert "_documentID=585819" in m["url"] and "locale=el" in m["url"]
    assert m["http"]["headers"] == {"content-length": "5", "content-type": "application/vnd.ms-excel",
                                    "date": "Tue, 14 Oct 2026 10:30:00 GMT"}
    assert rep.unrecorded == 6     # the five files the headers don't vouch for, and the extra copy


def test_seed_takes_hand_downloaded_microdata_from_their_checksum_list(tmp_path):
    """PY-BACKFILL-007: seeding takes hand-downloaded microdata listed in their checksum file

    Given a folder elstat-puf/hbs/archives with HBS_2019.zip, a SHA256SUMS line for it and one for a file that isn't there
    When the archive is seeded from it
    Then HBS_2019.zip is stored as elstat/puf-hbs-2019, of kind "manual" and with no URL
    And the missing file is ignored
    """
    folder = tmp_path / "research" / "elstat-puf" / "hbs" / "archives"
    folder.mkdir(parents=True)
    (folder / "HBS_2019.zip").write_bytes(b"zip")
    (folder / "SHA256SUMS").write_text(f"{_sha(b'zip')}  HBS_2019.zip\n{_sha(b'x')}  HBS_2020.zip\n", encoding="utf-8")
    archive = Archive(tmp_path / "archive")
    assert seed(archive, tmp_path / "research").stored == ["elstat/puf-hbs-2019"]
    m = archive.manifest(archive.latest("elstat", "puf-hbs-2019"))
    assert m["kind"] == "manual" and m.get("url") is None


def test_seed_skips_rows_it_cant_vouch_for_and_files_listed_twice(tmp_path):
    """PY-BACKFILL-008: seeding reports rows it can't vouch for, and copies a file listed twice only once

    Given a research folder without a date in its name, whose MANIFEST.md and README.md both list one good file with its date and checksum
    And a manifest row for a file that isn't there, a row with no date, and a row without a URL
    And a notes file that is neither a manifest nor a README
    When the archive is seeded from it as a dry run
    Then the good file is listed once
    And the missing file and the undated row are reported as skipped
    And the row without a URL and the notes file are ignored
    """
    folder = tmp_path / "research" / "pass"
    folder.mkdir(parents=True)
    (folder / "good.xlsx").write_bytes(b"good")
    (folder / "undated.xlsx").write_bytes(b"u")
    row = f"| good.xlsx | {ELSTAT_DOC.format(1)} | 2026-10-17 | {_sha(b'good')} |\n"
    head = "| File | Source URL | Downloaded | SHA-256 |\n|---|---|---|---|\n"
    (folder / "MANIFEST.md").write_text(
        head + row + f"| missing.xlsx | {ELSTAT_DOC.format(2)} | 2026-10-17 | {_sha(b'm')} |\n"
        f"| undated.xlsx | {ELSTAT_DOC.format(3)} | unknown | {_sha(b'u')} |\n"
        "| local.xlsx | (none) | 2026-10-17 | |\n", encoding="utf-8")
    (folder / "README.md").write_text(head + row, encoding="utf-8")
    (folder / "notes.md").write_text(head + f"| notes.xlsx | {ELSTAT_DOC.format(4)} | 2026-10-17 | {_sha(b'n')} |\n",
                                     encoding="utf-8")
    rep = seed(Archive(tmp_path / "archive"), tmp_path / "research", dry_run=True)
    assert rep.stored == ["elstat/doc-1 <- good.xlsx (2026-10-17)"]
    assert sorted(s.split(": ")[0].rsplit("/", 1)[1] for s in rep.skipped) == ["missing.xlsx", "undated.xlsx"]
