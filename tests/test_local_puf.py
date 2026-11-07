"""The PUF reader on synthetic surveys written in each era's layout. No real microdata here."""

import io
import zipfile
from datetime import UTC, datetime

import pytest

pytest.importorskip("pandas")
py7zr = pytest.importorskip("py7zr")

from traceconomics.archive.store import Archive  # noqa: E402
from traceconomics.checks import FormatError  # noqa: E402
from traceconomics.local import puf  # noqa: E402

pytestmark = pytest.mark.integration

N = 120  # households; the reader refuses implausibly small files


def households(era: str) -> tuple[str, str]:
    """(household csv, person csv) for N made-up households of two people each."""
    sep = "," if era == "2023" else ";"
    total = "C" if era in ("2016", "2024") else ""
    head = ["HA04", "HA06", "HA07", "HA08", "HA10", "HH095", "HH099", "HI11", "HB074",
            "HE01A", "HE01B", f"HE01{total}", "HE0111A", "HE0111B", f"HE0111{total}", "HE12704A", "HE12704B"]
    activity = "ME01\u00c1" if era == "2020" else "ME01"      # 2020 spells it with a garbled letter
    rows, people = [sep.join(head)], [sep.join(["MA04", "MB03", "MB05", activity]
                                               + (["HA07"] if era in ("2023", "2024") else []))]
    for i in range(N):
        cluster = f"{30000000 + i // 6}"
        if era == "2023":
            hh = str(i % 6 + 1)
        elif era == "2024":
            hh = f"{cluster}{i % 6 + 1:02d}"
        else:
            hh = f"{100 + i}"
        def dec(x):
            text = f"{x:.2f}".replace(".", ",")
            return f'"{text}"' if sep == "," else text
        values = [hh, f"{i % 3}", cluster, "EL30", dec(1000 + i), dec(8000 + 100 * i), dec(10000 + 100 * i), "1", "4",
                  dec(120), dec(30), dec(150), dec(100), dec(0), dec(100), dec(5), dec(1)]
        rows.append(sep.join(values))
        acts = ("Z1", "Z8") if era == "2020" else ("1", "8")        # 2020's re-ordered codes
        for person, age, relation, act in ((1, 45, "1", acts[0]), (2, 10, "3", acts[1])):
            if era == "2023":
                ma04, extra = f"{i % 6 + 1:02d}{person:02d}", [cluster]
            elif era == "2024":
                ma04, extra = f"9{i % 6 + 1:02d}{person:02d}", [cluster]
            elif era == "2020":
                ma04, extra = hh, []
            else:
                ma04, extra = f"{hh}{person:02d}", []
            people.append(sep.join([ma04, str(age), relation, act] + extra))
    return "\n".join(rows) + "\n", "\n".join(people) + "\n"


def archived(tmp_path, year: int, era: str, fmt: str, hh_text=None, p_text=None) -> Archive:
    hh, pp = households(era)
    hh, pp = hh_text or hh, p_text or pp
    names = {f"folder/hbs_hs_basic_{year}.csv": hh, f"folder/hbs_hm_basic_{year}.csv": pp, "folder/codebook.pdf": "x"}
    buf = io.BytesIO()
    if fmt == "zip":
        with zipfile.ZipFile(buf, "w") as z:
            for n, t in names.items():
                z.writestr(n, t)
    else:
        with py7zr.SevenZipFile(buf, "w") as z:
            for n, t in names.items():
                z.writestr(t.encode("latin-1"), n)
    archive = Archive(tmp_path / "archive")
    archive.store_bytes("elstat", puf.dataset(year), buf.getvalue(), url=None,
                        retrieved_at=datetime(2026, 10, 14, tzinfo=UTC), ext=f".{fmt}", kind="manual")
    return archive


@pytest.mark.parametrize("year,era,fmt,link", [
    (2016, "2016", "7z", "MA04 = household + person number"),
    (2020, "2020", "zip", "MA04 is the household"),
    (2023, "2023", "zip", "cluster - household number in MA04"),
    (2024, "2024", "zip", "cluster + 2 digits of MA04"),
])
def test_each_era_reads_the_same(tmp_path, year, era, fmt, link):
    """PY-PUF-001: every era's PUF layout reads the same

    Given a synthetic HBS PUF of 120 households of two persons, written in one era's layout and archive format
    When the year is read from the archive
    Then the person link is the one that era uses
    And every household and both persons of each are read, with no household left without persons
    And a decimal comma is read as a decimal (weight 1001.0)
    And division 01 is 150.0 in all modes and 120.0 in purchases
    And 12704 is derived as a total, 6.0 for the first household
    And the design is "full"
    And the persons' relation and activity are read, 2020's codes taken as the older ones where they mean the same
    And every household has ELSTAT's household type "4"
    And the classification is "coicop2018" from 2024 and "ecoicop1" before

    The outline runs 2016 (7z), 2020, 2023 and 2024 (zip).
    """
    s = puf.read(archived(tmp_path, year, era, fmt), year)
    assert s.person_link == link
    assert len(s.households) == N and len(s.persons) == 2 * N and not s.households_without_persons
    assert s.households.weight.iloc[1] == pytest.approx(1001.0)            # decimal comma read as a decimal
    assert s.spending["01"].iloc[0] == pytest.approx(150.0)               # the all-modes total
    assert s.purchases["01"].iloc[0] == pytest.approx(120.0)
    assert s.derived_totals == ("12704",) and s.spending["12704"].iloc[0] == pytest.approx(6.0)
    assert s.design == "full"
    # 2020's codes are read as the older ones where they mean the same (Z1 employed = 1 working).
    assert s.persons[["relation", "activity"]].iloc[:2].values.tolist() == [["1", "1"], ["3", "Z8" if year == 2020 else "8"]]
    assert (s.households.elstat_type == "4").all()
    assert s.classification == ("coicop2018" if year >= 2024 else "ecoicop1")


def test_total_that_isnt_purchases_plus_non_monetary_is_refused(tmp_path):
    """PY-PUF-002: a total that isn't purchases plus non-monetary spending is refused

    Given a synthetic 2016 PUF where one household's division 01 total is off by 1
    When it is read
    Then a FormatError saying the total "isn't purchases" plus the rest is raised
    """
    hh, pp = households("2016")
    hh = hh.replace(";150,00;", ";151,00;", 1)
    with pytest.raises(FormatError, match="isn't purchases"):
        puf.read(archived(tmp_path, 2016, "2016", "7z", hh_text=hh), 2016)


def test_person_without_a_household_is_refused(tmp_path):
    """PY-PUF-003: a person without a household is refused

    Given a synthetic 2016 PUF with a person whose household doesn't exist
    When it is read
    Then a FormatError about the person link is raised
    """
    hh, pp = households("2016")
    pp += "99999901;30;1;1\n"
    with pytest.raises(FormatError, match="person-link"):
        puf.read(archived(tmp_path, 2016, "2016", "7z", p_text=pp), 2016)


def test_missing_year_says_how_to_add_it(tmp_path):
    """PY-PUF-004: a year not in the archive says how to add it

    Given an empty archive
    When the 2030 survey is read
    Then a FormatError pointing to "traceconomics import" is raised
    """
    with pytest.raises(FormatError, match="traceconomics import"):
        puf.read(Archive(tmp_path / "a"), 2030)


def test_unknown_activity_code_is_refused(tmp_path):
    """PY-PUF-005: an activity code unknown to that year is refused

    Given a synthetic 2016 PUF with a 2020-style activity code
    When it is read
    Then a FormatError about the ME01 codes is raised
    """
    hh, pp = households("2016")
    pp = pp.replace(";45;1;1\n", ";45;1;Z1\n", 1)                  # a 2020 code in an older file
    with pytest.raises(FormatError, match="ME01 codes"):
        puf.read(archived(tmp_path, 2016, "2016", "7z", p_text=pp), 2016)
