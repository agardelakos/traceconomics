"""The mapping to COICOP 2018: RAS, weights, both tables, applying them. Made-up numbers; the package's
own mapping tables (aggregates, no microdata) are read where a test applies them."""

import pytest

pd = pytest.importorskip("pandas")
np = pytest.importorskip("numpy")

from traceconomics.local import mapping, mapping_check  # noqa: E402
from traceconomics.local.puf import Survey  # noqa: E402


def links(pairs):
    return pd.DataFrame(pairs, columns=["v1", "v2"])


def test_ras_fits_both_totals_where_the_links_allow():
    fitted, report = mapping.ras(links([("A", "x"), ("A", "y"), ("B", "y")]),
                                 pd.Series({"A": 3.0, "B": 1.0}), pd.Series({"x": 2.0, "y": 2.0}))
    assert fitted[("A", "x")] == pytest.approx(2.0) and fitted[("A", "y")] == pytest.approx(1.0)
    assert fitted[("B", "y")] == pytest.approx(1.0)
    assert report["max_col_error"] < 1e-8 and report["components"] == 1


def test_ras_with_conflicting_totals_keeps_rows_exact_and_reports_the_misfit():
    # Separate link groups are each scaled to their own row total, so they never conflict.
    fitted, report = mapping.ras(links([("A", "x"), ("B", "y")]),
                                 pd.Series({"A": 1.0, "B": 3.0}), pd.Series({"x": 2.0, "y": 2.0}))
    assert fitted[("A", "x")] == pytest.approx(1.0) and fitted[("B", "y")] == pytest.approx(3.0)
    assert report["components"] == 2 and report["max_col_error"] < 1e-8
    # y wants 1.8 of 2, but only B (1.0) can give to it: no exact fit exists.
    fitted, report = mapping.ras(links([("A", "x"), ("B", "x"), ("B", "y")]),
                                 pd.Series({"A": 1.0, "B": 1.0}), pd.Series({"x": 0.2, "y": 1.8}))
    assert fitted.groupby(level=0).sum()["A"] == pytest.approx(1.0)
    assert report["max_col_error"] > 0.5 and report["misfit"]["B"] > 0.5


def test_ras_ignores_rows_and_columns_without_weight():
    fitted, _ = mapping.ras(links([("A", "x"), ("A", "y"), ("Z", "x")]),
                            pd.Series({"A": 2.0, "Z": 0.0}), pd.Series({"x": 1.0, "y": 0.0}))
    assert list(fitted.index) == [("A", "x")]


def test_subclass_weights_take_a_lone_subclass_from_its_published_parent():
    w = pd.Series({"0411": 30.0, "063": 17.6, "0451": 9.0, "04511": 5.0, "04512": 4.0, "0452": 3.0})
    got = mapping.subclass_weights(w, ["04110", "06300", "04511", "04512", "04521", "04522"])
    assert got["04110"] == 30.0 and got["06300"] == 17.6 and got["04511"] == 5.0
    assert got["04521"] == 0.0 and got["04522"] == 0.0                     # two subclasses: 0452 isn't split


def test_v1_table_methods_and_shares():
    lk = links([("01110", "01110"),                                       # single link
                ("02000", "02001"), ("02000", "02002"), ("02100", "02002"),  # RAS
                ("03000", "03001"), ("03000", "03002"),                   # no source weight
                ("04000", "04001"), ("04000", "04002")])                  # no weights at all
    w1 = pd.Series({"01110": 5.0, "02000": 4.0, "02100": 1.0})
    w2 = pd.Series({"01110": 5.0, "02001": 3.0, "02002": 2.0, "03001": 1.0, "03002": 3.0})
    table, report = mapping.build_v1_to_2018(lk, w1, w2)
    by = table.set_index(["from_code", "to_code"])
    assert by.loc[("01110", "01110"), "method"] == "single link"
    assert by.loc[("02000", "02001"), "share"] == pytest.approx(0.75)        # 3 of A's 4; B fills y's 1
    assert by.loc[("02000", "02001"), "method"] == "RAS on 2025 weights"
    assert by.loc[("03000", "03002"), "share"] == pytest.approx(0.75)
    assert by.loc[("03000", "03002"), "method"].startswith("targets' 2025 weights")
    assert by.loc[("04000", "04001"), "share"] == pytest.approx(0.5)
    assert np.allclose(table.groupby("from_code").share.sum(), 1.0)


def test_old_list_bridge():
    old = {
        "01111": mapping.OldList("01111", {2013: "Rice", 2014: "Rice"}),          # same code and label
        "01112": mapping.OldList("01112", {2014: "Bread"}),                       # number reused for flour
        "01113": mapping.OldList("01113", {2014: "Pasta"}),
        "063": mapping.OldList("063", {2014: "Hospital services"}),               # older 3-digit code
        "0231": mapping.OldList("0231", {2014: ""}),                              # nothing under 0231
    }
    v1_labels = {"01111": "Rice", "01112": "Flours and other cereals", "01113": "Bread", "01114": "Other bakery"}
    spend = pd.Series({"01111": 10.0, "01112": 1.0, "01113": 6.0, "01114": 3.0, "06300": 7.0, "02300": 0.0})
    t = mapping.build_old_to_v1(old, v1_labels, spend).set_index(["from_code", "to_code"])
    assert t.loc[("01111", "01111"), "method"] == "same code and label"
    # 01112 and 01113 share the rest of class 0111 (not rice, which 01111 took) by 2015 spending.
    assert t.loc[("01112", "01113"), "share"] == pytest.approx(0.6)
    assert ("01112", "01111") not in t.index
    assert t.loc[("063", "06300"), "share"] == 1.0 and "group 063" in t.loc[("063", "06300"), "method"]
    assert t.loc[("0231", "02300"), "method"].startswith("equal split over 023")


def survey(year, columns):
    h = pd.DataFrame({"hh": ["a", "b"], "weight": [1.0, 2.0], "region": "EL3", "stratum": None, "cluster": None,
                      "money_income": [1.0, 2.0], "total_income": [1.0, 2.0], "main_income_source": "1"})
    leaf = pd.DataFrame(columns, index=[0, 1], dtype=float)
    s = mapping.with_parents(leaf)
    from traceconomics.local.puf import classification
    return Survey(year=year, classification=classification(year), households=h,
                  persons=pd.DataFrame({"hh": ["a", "b"], "age": [40, 40]}), spending=s, purchases=s.copy(),
                  design="full", source_sha256="0" * 64)


@pytest.mark.parametrize("year,columns", [
    (2016, {"04110": [100, 0], "06110": [50, 20], "12132": [10, 40], "09141": [5, 5]}),
    (2010, {"04111": [100, 0], "063": [30, 0], "01112": [8, 2], "02211": [0, 9]}),
])
def test_to_2018_keeps_every_household_total_and_adds_parents(year, columns):
    s = survey(year, columns)
    m = mapping.to_2018(s)
    from traceconomics.local.shares import leaves
    assert m.classification == "coicop2018"
    before = s.spending[leaves(s.spending.columns)].sum(axis=1)
    after = m.spending[leaves(m.spending.columns)].sum(axis=1)
    assert np.allclose(before, after)
    for parent in {c[:2] for c in leaves(m.spending.columns)}:
        under = [c for c in leaves(m.spending.columns) if c.startswith(parent)]
        assert np.allclose(m.spending[parent], m.spending[under].sum(axis=1))
    assert mapping.to_2018(m) is m                                        # already COICOP 2018


def test_to_2018_refuses_a_code_with_no_mapping():
    from traceconomics.checks import FormatError
    with pytest.raises(FormatError, match="no mapping"):
        mapping.to_2018(survey(2016, {"99999": [1, 1]}))


def test_package_tables_add_up_and_chain():
    v1, old = mapping.load(mapping.V1_TO_2018), mapping.load(mapping.OLD_TO_V1)
    assert set(old.to_code) <= set(v1.from_code)
    assert v1.to_code.str.fullmatch(r"\d{5}").all() and v1.from_code.str.fullmatch(r"\d{5}").all()


def test_exposure_counts_only_what_a_split_decided():
    s = survey(2016, {"01110": [10, 10], "02000": [0, 0]})
    table = pd.DataFrame({"from_code": ["01110", "01110"], "to_code": ["01110", "02110"], "share": [0.9, 0.1]})
    e = mapping_check.exposure(s, table)
    # 01110 sends 90% to division 01: at stake min(0.9, 0.1) of its 30 = 3, of 01's 27.
    assert e["01"] == pytest.approx(3 / 27)
    assert e["02"] == pytest.approx(1.0)                                  # all of 02's 3 came from the split
