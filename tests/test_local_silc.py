"""EU-SILC microdata: tenure and rent paid by household and person, on a made-up survey."""

import io

import pytest

pd = pytest.importorskip("pandas")
py7zr = pytest.importorskip("py7zr")

from traceconomics.archive.store import Archive  # noqa: E402
from traceconomics.checks import FormatError  # noqa: E402
from traceconomics.local import silc  # noqa: E402

pytestmark = pytest.mark.integration


def _archive_with(tmp_path, year, h_rows, d_weights, persons, tenure_col="HH021"):
    """An archive holding a made-up SILC file for `year` in the layout ELSTAT uses: a 7z with one
    '... Public Use Files.xlsx' (sheets D_FILE, H_FILE, R_FILE) and a description workbook."""
    buf = io.BytesIO()
    with pd.ExcelWriter(buf) as xw:
        pd.DataFrame({"DB030": list(d_weights), "DB090": list(d_weights.values())}).to_excel(xw, sheet_name="D_FILE", index=False)
        pd.DataFrame([{"HB030": h, tenure_col: t, "HH060": r} for h, t, r in h_rows]).to_excel(xw, sheet_name="H_FILE", index=False)
        pd.DataFrame([{"RB030": f"{h}0{i}", "RB040": h, "RB050": w} for i, (h, w) in enumerate(persons)]).to_excel(
            xw, sheet_name="R_FILE", index=False)
    src = tmp_path / "src"
    src.mkdir(parents=True)
    (src / f"SILC_{year}_Public Use Files.xlsx").write_bytes(buf.getvalue())
    (src / "description.xlsx").write_bytes(b"not read")
    seven = tmp_path / f"silc{year}.7z"
    with py7zr.SevenZipFile(seven, "w") as z:
        for p in sorted(src.iterdir()):
            z.write(p, p.name)
    archive = Archive(tmp_path / "archive")
    archive.store_file("elstat", f"puf-statistics-on-income-and-living-conditions-silc-{year}", seven, url=None,
                       retrieved_at=pd.Timestamp("2026-10-14", tz="UTC").to_pydatetime(), ext=".7z", kind="manual",
                       move=False)
    return archive


H = [("1", "1", ""), ("2", "3", "400"), ("3", "4", "200.5"), ("4", "5", "")]
D = {"1": 100.0, "2": 50.0, "3": 10.0, "4": 40.0}
P = [("1", 100.0), ("1", 100.0), ("2", 50.0), ("3", 10.0), ("4", 40.0)]


def test_tenure_and_rent_by_household_and_person(tmp_path):
    """PY-SILC-001: the SILC table gives tenure and rent paid by household and person, from the archived file read in memory

    Given an archive with a made-up SILC 2024 file: an owner (weight 100, two people), a market renter paying 400 a month (weight 50), a reduced-rent renter paying 200.50 (weight 10) and a household housed free (weight 40)
    When its tenure table is made
    Then renters are 60 of 200 weighted households, 50 at market rent and 10 at reduced rent
    And the owners count 200 people weighted
    And rent paid is twelve months of 50 × 400 + 10 × 200.50, 264,060 euros a year, all of it the renters'
    And household counts under 20 are written "<20"
    """
    a = _archive_with(tmp_path, 2024, H, D, P)
    assert silc.years(a) == {2024: "puf-statistics-on-income-and-living-conditions-silc-2024"}
    t = silc.table(silc.read(a, 2024), 2024, "v").set_index("tenure")
    assert t.loc["all", "households_weighted"] == 200.0 and t.loc["renter", "households_weighted"] == 60.0
    assert (t.loc["renter_market", "households_weighted"], t.loc["renter_reduced", "households_weighted"]) == (50.0, 10.0)
    assert t.loc["owner", "people_weighted"] == 200.0
    assert t.loc["all", "rent_paid_eur"] == pytest.approx(12 * (50 * 400 + 10 * 200.5))
    assert t.loc["renter", "rent_paid_eur"] == t.loc["all", "rent_paid_eur"]
    assert (t.n_households == "<20").all()


def test_run_archives_the_table_once(tmp_path):
    """PY-SILC-002: the SILC run archives each year's table once, as oet-local

    Given the made-up SILC 2024 file in an archive
    When the SILC run is made twice
    Then the first run stores oet-local/silc-tenure-gr-2024 and reports renters at 30% of households
    And the second run finds it unchanged
    And the table's header names its provenance
    """
    a = _archive_with(tmp_path, 2024, H, D, P)
    first = silc.run(a)[0]
    assert first["result"] == "stored" and first["renters_households"] == 0.3
    assert silc.run(a)[0]["result"] == "unchanged"
    text = (a.root / a.latest("oet-local", "silc-tenure-gr-2024")["path"]).read_text(encoding="utf-8")
    assert text.startswith("# Greek EU-SILC 2024") and '"survey": "elstat/puf-statistics-on-income' in text


def test_older_files_use_hh020_and_unknown_codes_are_refused(tmp_path):
    """PY-SILC-003: a 2003-2009 file's tenure is read from HH020 with its own codes; an unknown code is refused

    Given a made-up SILC 2009 file whose only tenure column is the older HH020 (1 owner, 2 market rent, 3 reduced rent, 4 rent-free)
    And a made-up SILC 2024 file with an HH021 code 7
    When each is tabled
    Then the 2009 file's renters are its market and reduced-rent households, 60 of 200
    And the 2024 file is refused with a FormatError naming the unknown code
    """
    old = _archive_with(tmp_path / "a", 2009, [("1", "1", ""), ("2", "2", "400"), ("3", "3", "200.5"), ("4", "4", "")],
                        D, P, tenure_col="HH020")
    t = silc.table(silc.read(old, 2009), 2009, "v").set_index("tenure")
    assert t.loc["renter", "households_weighted"] == 60.0 and t.loc["rent_free", "households_weighted"] == 40.0
    bad = _archive_with(tmp_path / "b", 2024, [*H[:3], ("4", "7", "")], D, P)
    with pytest.raises(FormatError, match="HH021 codes not in ELSTAT's list"):
        silc.table(silc.read(bad, 2024), 2024, "v")
