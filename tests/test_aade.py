"""AADE's personal income tax statistics: the workbook links on its page, and table 1's national
totals read as published."""

from pathlib import Path

import pytest

from traceconomics.checks import FormatError
from traceconomics.sources import aade
from traceconomics.sources.aade import parse

pytestmark = pytest.mark.integration

FIX = Path(__file__).parent / "fixtures"


def test_page_lists_each_years_workbook_once():
    """PY-AADE-001: the statistics page gives each yearly workbook once, as an absolute address

    Given AADE's saved page of yearly personal income tax statistics
    When its workbook links are read
    Then the tax year 2022 workbook comes first, as an absolute address on www.aade.gr
    And no address repeats, and every one ends in .xlsx
    And each gets its own archive dataset, named after the file
    """
    links = aade.workbook_links((FIX / "aade_annual_reports_natural_persons_en.html").read_text(encoding="utf-8"))
    assert links[0] == "https://www.aade.gr/sites/default/files/2024-05/SD_FP_22F_3.xlsx"
    assert len(links) == len(set(links)) and all(u.endswith(".xlsx") for u in links)
    assert aade.dataset_for(links[0]) == "pit-sd-fp-22f-3"
    assert len({aade.dataset_for(u) for u in links}) == len(links)


def test_table_1_gives_aades_own_national_totals():
    """PY-AADE-002: table 1 gives AADE's own all-regions totals, the text kept as published

    Given AADE's workbook for tax year 2022
    When table 1 is read
    Then every kept row has one value for 2022, from the all-regions "per return" column
    And the returns are 6,560,865 and the declared income 91,674,362,821.89 euros, the text exactly as in the file
    And the declared income from property is 7,857,453,360.18 euros
    """
    got = {m: (u, p, text, v) for m, u, p, text, v in parse.rows(FIX / "aade_SD_FP_22F_3.xlsx")}
    assert set(got) == set(parse.MEASURES.values())
    assert {p for _, p, _, _ in got.values()} == {"2022"}
    assert got["returns"][0] == "NR" and got["returns"][2] == "6560865"
    assert got["declared_income"] == ("EUR", "2022", "91674362821.89", 91674362821.89)
    assert got["declared_income_property"][2] == "7857453360.18"


def test_a_workbook_in_another_layout_is_refused(tmp_path):
    """PY-AADE-003: a workbook without table 1's layout is refused

    Given a made-up workbook with a sheet Π1 that lacks the all-regions column
    When it is read
    Then a FormatError is raised, naming what is missing
    """
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Π1"
    ws.append(["Φορολογικό Έτος 2023"])
    ws.append(["", "Αττικής"])
    ws.append(["Μετρήσιμο - Περιγραφή", "Δήλωση"])
    ws.append(["1.ΑΡΙΘΜΟΣ ΦΟΡΟΛΟΓΟΥΜΕΝΩΝ", "1"])
    path = tmp_path / "other.xlsx"
    wb.save(path)
    with pytest.raises(FormatError, match="Σύνολο Περιφεριών"):
        parse.rows(path)
