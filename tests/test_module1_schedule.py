"""The weights-timing rule on made-up release calendars."""

from datetime import date

from traceconomics.module1.schedule import FINAL, FIRST, releases, rule_n


def cal(**dates):
    return {int(y[1:]): {"available": date.fromisoformat(d), "basis": "test"} for y, d in dates.items()}


def test_final_where_the_year_before_is_held_else_the_newest_available_in_january():
    surveys = {2021, 2022, 2023, 2024}
    s = rule_n(range(2022, 2027), surveys, cal(y2023="2025-05-07", y2024="2026-04-01"))
    assert [(e.year, e.survey, e.status) for e in s] == [
        (2022, 2021, FINAL), (2023, 2022, FINAL), (2024, 2023, FINAL), (2025, 2024, FINAL), (2026, 2023, FIRST)]
    assert s[-1].valid_from == "2026-01" and "2025-05-07" in s[-1].basis


def test_no_candidate_ends_the_schedule():
    s = rule_n(range(2026, 2029), {2024}, cal(y2024="2026-04-01"))
    assert s == []                                    # nothing was out on 2026-01-01


def test_package_release_dates_load():
    r = releases()
    assert r[2024]["available"] == date(2026, 4, 1) and r[2024]["basis"] == "folder"


def test_rule_f_fixed_lag_starts_at_the_first_held_survey_and_never_revises():
    from traceconomics.module1.schedule import rule_f
    s = rule_f(range(2009, 2027), set(range(2008, 2025)))
    assert s[0].year == 2011 and s[0].survey == 2008            # 2009-2010 would need 2006-2007
    assert [(e.year, e.survey) for e in s[-3:]] == [(2024, 2021), (2025, 2022), (2026, 2023)]
    assert {e.status for e in s} == {FINAL}


def test_rule_f_2026_equals_rule_n_first_estimate_with_the_package_dates():
    from traceconomics.module1.schedule import rule_f
    surveys = set(range(2008, 2025))
    n = {e.year: e for e in rule_n(range(2009, 2027), surveys)}
    f = {e.year: e for e in rule_f(range(2009, 2027), surveys)}
    assert n[2026].status == FIRST and n[2026].survey == f[2026].survey == 2023


def test_rule_u_same_year_and_stops_at_the_newest_survey():
    from traceconomics.module1.schedule import rule_u
    s = rule_u(range(2009, 2027), set(range(2008, 2025)))
    assert (s[0].year, s[0].survey, s[-1].year) == (2009, 2009, 2024)
    assert all(e.year == e.survey for e in s)


def test_a_missing_survey_ends_rule_f_rather_than_skipping_a_year():
    from traceconomics.module1.schedule import rule_f
    s = rule_f(range(2011, 2020), {2008, 2009, 2011, 2012})
    assert [e.year for e in s] == [2011, 2012]                  # 2013 needs 2010
