import hashlib
from datetime import date

from traceconomics.archive.store import Archive
from traceconomics.backfill import dataset_for_url, import_file, seed

ELSTAT_DOC = "https://www.statistics.gr/en/statistics?_documentID={}&_locale=en"
EUROSTAT_DATA = "https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/data/"


def _sha(b):
    return hashlib.sha256(b).hexdigest()


def test_dataset_for_url():
    assert dataset_for_url("https://www.statistics.gr:443/en/statistics?x=1&_documentID=585819&_locale=en") == ("elstat", "doc-585819")
    assert dataset_for_url("https://www.statistics.gr/el/statistics?_documentID=114834&_locale=el") == ("elstat", "doc-114834-el")
    assert dataset_for_url(EUROSTAT_DATA + "prc_hicp_fp?format=TSV&compressed=true") == ("eurostat", "prc_hicp_fp")
    assert dataset_for_url(EUROSTAT_DATA + "prc_hicp_fp?format=SDMX-CSV&compressed=true") == ("eurostat", "prc_hicp_fp-full-sdmx-csv")
    assert dataset_for_url(EUROSTAT_DATA + "prc_hicp_manr/M.RCH_A.CP00.EL/?format=SDMX-CSV")[1] == "prc_hicp_manr-extract-sdmx-csv"
    assert dataset_for_url("https://www.bankofgreece.gr/paper.pdf") is None


def test_seed_copies_verified_files_only(tmp_path):
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
    f = tmp_path / "HBS_2025.zip"
    f.write_bytes(b"zip")
    archive = Archive(tmp_path / "archive")
    r = import_file(archive, f, source="elstat", dataset=None, url=None, downloaded=date(2026, 4, 2), note=None)
    assert r.status == "stored" and r.dataset == "puf-hbs-2025" and f.exists()
    assert archive.manifest(archive.latest("elstat", "puf-hbs-2025"))["kind"] == "manual"
