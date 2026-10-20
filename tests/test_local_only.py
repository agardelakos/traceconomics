"""Microdata never leave the owner's machine: the rule is in code, not in memory."""

import pytest

from traceconomics.archive.local_only import LocalOnlyError, check, is_local_only


@pytest.mark.parametrize("dataset", ["puf-hbs-2024", "puf-lfs-puf-2025a-gr", "puf-statistics-on-income-and-living-conditions-silc-2025"])
def test_puf_files_are_local_only(dataset):
    assert is_local_only("elstat", dataset)


@pytest.mark.parametrize("source,dataset", [("elstat", "puf-catalogue"), ("elstat", "doc-585819"),
                                            ("eurostat", "prc_hicp_minr")])
def test_public_files_are_not(source, dataset):
    # The microdata catalogue page is public: an explicit exception to the broad pattern.
    assert not is_local_only(source, dataset)


def test_a_new_microdata_name_is_still_caught():
    assert is_local_only("elstat", "puf-some-future-survey-2031")


def test_check_refuses_microdata():
    check([("eurostat", "prc_hicp_minr"), ("elstat", "doc-585819")])
    with pytest.raises(LocalOnlyError, match="puf-hbs-2024"):
        check([("eurostat", "prc_hicp_minr"), ("elstat", "puf-hbs-2024")])
