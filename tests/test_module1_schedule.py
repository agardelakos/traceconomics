"""The weights-timing rule on made-up release calendars."""

from datetime import date

import pytest

from traceconomics.module1.schedule import FINAL, FIRST, releases, rule_n

pytestmark = pytest.mark.unit


def cal(**dates):
    return {int(y[1:]): {"available": date.fromisoformat(d), "basis": "test"} for y, d in dates.items()}


def test_final_where_the_year_before_is_held_else_the_newest_available_in_january():
    """PY-SCHED-001: final weights where the year before is held, else the newest out in January

    Given surveys 2021 to 2024 and release dates for 2023 and 2024
    When rule N is applied to index years 2022 to 2026
    Then 2022 to 2025 use the year before's survey as final weights
    And 2026 uses survey 2023 as a first estimate, valid from 2026-01, its basis naming 2023's release date
    """
    surveys = {2021, 2022, 2023, 2024}
    s = rule_n(range(2022, 2027), surveys, cal(y2023="2025-05-07", y2024="2026-04-01"))
    assert [(e.year, e.survey, e.status) for e in s] == [
        (2022, 2021, FINAL), (2023, 2022, FINAL), (2024, 2023, FINAL), (2025, 2024, FINAL), (2026, 2023, FIRST)]
    assert s[-1].valid_from == "2026-01" and "2025-05-07" in s[-1].basis


def test_no_candidate_ends_the_schedule():
    """PY-SCHED-002: with no survey out in time, the schedule is empty

    Given only survey 2024, released on 2026-04-01
    When rule N is applied to index years 2026 to 2028
    Then the schedule is empty, since nothing was out on 2026-01-01
    """
    s = rule_n(range(2026, 2029), {2024}, cal(y2024="2026-04-01"))
    assert s == []                                    # nothing was out on 2026-01-01


def test_package_release_dates_load():
    """PY-SCHED-003: the package's release dates load

    Given the package's survey release dates
    When they are loaded
    Then survey 2024 was available on 2026-04-01, on basis "folder"
    """
    r = releases()
    assert r[2024]["available"] == date(2026, 4, 1) and r[2024]["basis"] == "folder"


def test_rule_f_fixed_lag_starts_at_the_first_held_survey_and_never_revises():
    """PY-SCHED-004: rule F's fixed lag starts at the first held survey and never revises

    Given surveys 2008 to 2024
    When rule F is applied to index years 2009 to 2026
    Then it starts at 2011 with survey 2008
    And it ends with 2024, 2025 and 2026 on surveys 2021, 2022 and 2023
    And every entry is final
    """
    from traceconomics.module1.schedule import rule_f
    s = rule_f(range(2009, 2027), set(range(2008, 2025)))
    assert s[0].year == 2011 and s[0].survey == 2008            # 2009-2010 would need 2006-2007
    assert [(e.year, e.survey) for e in s[-3:]] == [(2024, 2021), (2025, 2022), (2026, 2023)]
    assert {e.status for e in s} == {FINAL}


def test_rule_f_2026_equals_rule_n_first_estimate_with_the_package_dates():
    """PY-SCHED-005: rule F's 2026 equals rule N's first estimate on the package's dates

    Given surveys 2008 to 2024 and the package's release dates
    When rules N and F are applied to index years 2009 to 2026
    Then rule N's 2026 is a first estimate
    And both use survey 2023 for 2026
    """
    from traceconomics.module1.schedule import rule_f
    surveys = set(range(2008, 2025))
    n = {e.year: e for e in rule_n(range(2009, 2027), surveys)}
    f = {e.year: e for e in rule_f(range(2009, 2027), surveys)}
    assert n[2026].status == FIRST and n[2026].survey == f[2026].survey == 2023


def test_rule_u_same_year_and_stops_at_the_newest_survey():
    """PY-SCHED-006: rule U uses the same year and stops at the newest survey

    Given surveys 2008 to 2024
    When rule U is applied to index years 2009 to 2026
    Then it runs from 2009 on survey 2009 to 2024
    And every year uses its own year's survey
    """
    from traceconomics.module1.schedule import rule_u
    s = rule_u(range(2009, 2027), set(range(2008, 2025)))
    assert (s[0].year, s[0].survey, s[-1].year) == (2009, 2009, 2024)
    assert all(e.year == e.survey for e in s)


def test_a_missing_survey_ends_rule_f_rather_than_skipping_a_year():
    """PY-SCHED-007: a missing survey ends rule F rather than skipping a year

    Given surveys 2008, 2009, 2011 and 2012
    When rule F is applied to index years 2011 to 2019
    Then only 2011 and 2012 are scheduled, since 2013 needs the missing 2010
    """
    from traceconomics.module1.schedule import rule_f
    s = rule_f(range(2011, 2020), {2008, 2009, 2011, 2012})
    assert [e.year for e in s] == [2011, 2012]                  # 2013 needs 2010


@pytest.mark.parametrize("rule, year", [("N", 2011), ("F", 2013), ("U", 2010)])
def test_the_2009_survey_stands_in_for_2010s_income_groups(rule, year):
    """PY-SCHED-010: wherever a rule would use the 2010 survey for a grouping ranked by income, the 2009 survey stands in

    Given surveys 2008 to 2024, the 2010 survey's income groups not built (its incomes can't rank households)
    When rules N, F and U are applied for the income fifths (B) and for tenure
    Then the index year each rule weighs with survey 2010 (2011, 2013, 2010) uses survey 2009 for the fifths, its basis saying why
    And the tenure groups still use survey 2010 there, and no other year changes
    """
    from traceconomics.module1.schedule import RULES, held_for_rule, with_stand_ins

    held = set(range(2008, 2025))
    income = with_stand_ins("B", RULES[rule](range(2009, 2026), held_for_rule("B", held - {2010})))
    tenure = with_stand_ins("tenure", RULES[rule](range(2009, 2026), held_for_rule("tenure", held)))
    by_income, by_tenure = {e.year: e for e in income}, {e.year: e for e in tenure}
    assert by_income[year].survey == 2009 and "standing in for survey 2010" in by_income[year].basis
    assert by_tenure[year].survey == 2010
    assert {y: e.survey for y, e in by_income.items() if y != year} == {y: e.survey for y, e in by_tenure.items() if y != year}
