"""Microdata never leave the owner's machine: the rule is in code, not in memory."""

import pytest

from traceconomics.archive.local_only import LocalOnlyError, check, is_local_only


@pytest.mark.parametrize("dataset", ["puf-hbs-2024", "puf-lfs-puf-2025a-gr", "puf-statistics-on-income-and-living-conditions-silc-2025"])
def test_puf_files_are_local_only(dataset):
    """PY-LOCAL-001: ELSTAT microdata files are local-only

    Given an ELSTAT microdata dataset name
    When it is checked
    Then it is local-only
    """
    assert is_local_only("elstat", dataset)


@pytest.mark.parametrize("source,dataset", [("elstat", "puf-catalogue"), ("elstat", "doc-585819"),
                                            ("eurostat", "prc_hicp_minr")])
def test_public_files_are_not(source, dataset):
    # The microdata catalogue page is public: an explicit exception to the broad pattern.
    """PY-LOCAL-002: public files are not local-only

    Given a public dataset, including ELSTAT's microdata catalogue page
    When it is checked
    Then it is not local-only

    The microdata catalogue page is public: an explicit exception to the broad pattern.
    """
    assert not is_local_only(source, dataset)


def test_a_new_microdata_name_is_still_caught():
    """PY-LOCAL-003: a new microdata name is still caught

    Given an ELSTAT microdata dataset name not yet in use
    When it is checked
    Then it is local-only
    """
    assert is_local_only("elstat", "puf-some-future-survey-2031")


def test_check_refuses_microdata():
    """PY-LOCAL-004: the check refuses a list that includes microdata

    Given a list of public datasets
    And a list that also includes puf-hbs-2024
    When each is checked
    Then the public list passes
    And the other raises a LocalOnlyError naming puf-hbs-2024
    """
    check([("eurostat", "prc_hicp_minr"), ("elstat", "doc-585819")])
    with pytest.raises(LocalOnlyError, match="puf-hbs-2024"):
        check([("eurostat", "prc_hicp_minr"), ("elstat", "puf-hbs-2024")])
