"""Category names in English and Greek: official wording, normal case, no gaps."""

import csv

import openpyxl
import pytest

from traceconomics.checks import FormatError
from traceconomics.export import labels


def test_clean_takes_off_the_notation_and_keeps_the_kind():
    assert labels.clean("01.1.1.1 Cereals (ND)") == ("Cereals", "non-durable")
    assert labels.clean("12.2.1 Υπηρεσίες χρηματοπιστωτικής διαμεσολάβησης (Υ)") == \
        ("Υπηρεσίες χρηματοπιστωτικής διαμεσολάβησης", "service")
    assert labels.clean("04.2 Imputed rental payments for housing") == ("Imputed rental payments for housing", None)


def write_eu(path, rows):
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["c", "notation", "label_en", "label_el"])
        for code, en, el in rows:
            w.writerow([f"http://data.europa.eu/ed1/ecoicop2/{code}", "", en, el])


def write_hbs(path, rows):
    book = openpyxl.Workbook()
    sheet = book.active
    for _ in range(4):
        sheet.append(["header"])
    for code, name in rows:
        sheet.append([2025, len(code), code, name, 1, 1.0])
    book.save(path)


def test_eu_names_first_then_elstat_with_capitals_replaced_by_the_single_child(tmp_path):
    write_eu(tmp_path / "eu.csv", [("011", "01.1 Food (ND)", "01.1 Τρόφιμα (ΜΔΑ)")])
    write_hbs(tmp_path / "en.xlsx", [("013", "SERVICES FOR PROCESSING"), ("0130", "Services for processing (S)")])
    write_hbs(tmp_path / "el.xlsx", [("013", "ΥΠΗΡΕΣΙΕΣ ΜΕΤΑΠΟΙΗΣΗΣ"), ("0130", "Υπηρεσίες μεταποίησης (Υ)")])
    out = labels.build(["011", "013"], tmp_path / "eu.csv", tmp_path / "en.xlsx", tmp_path / "el.xlsx")
    assert out["011"] == {"en": "Food", "el": "Τρόφιμα", "kind": "non-durable", "source": "eu-vocabularies"}
    assert out["013"]["el"] == "Υπηρεσίες μεταποίησης" and out["013"]["source"] == "elstat-hbs"


def test_a_name_only_in_capitals_or_missing_stops_the_export(tmp_path):
    write_eu(tmp_path / "eu.csv", [])
    write_hbs(tmp_path / "en.xlsx", [("014", "SOMETHING"), ("0141", "Other words")])
    write_hbs(tmp_path / "el.xlsx", [("014", "ΚΑΤΙ"), ("0141", "Άλλες λέξεις")])
    with pytest.raises(FormatError, match="014"):
        labels.build(["014"], tmp_path / "eu.csv", tmp_path / "en.xlsx", tmp_path / "el.xlsx")
    with pytest.raises(FormatError, match="099"):
        labels.build(["099"], tmp_path / "eu.csv", tmp_path / "en.xlsx", tmp_path / "el.xlsx")
