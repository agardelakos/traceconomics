"""The consistency topic: the overview of every check, a check's page with its differences, a
written finding, a question across sources, and the ways in (the country card, the Groups page,
the data page). Expected values come from the exported checks.json."""

import json
import urllib.request

import pytest
from selenium.webdriver.common.action_chains import ActionChains

from helpers import DIST, num, t

M5 = "/{lang}/gr/official-figures-consistency/"
DATA = "/data/v1/gr/m5/latest"


def _results() -> dict:
    return json.loads((DIST / DATA.lstrip("/") / "checks.json").read_text(encoding="utf-8"))


def _status(c: dict) -> str:
    unknown, differ = c["differ"].get("not-known", 0), c["compared"] - c["agree"]
    return "agree" if differ == 0 else "explained" if unknown == 0 else "partly" if unknown < differ else "unknown"


def _get(base_url: str, path: str) -> tuple[int, bytes]:
    with urllib.request.urlopen(base_url + path, timeout=30) as r:
        return r.status, r.read()


@pytest.mark.parametrize("lang", ["en", "el"])
def test_overview_lists_every_check(site, lang):
    """SEL-M5-001: the overview lists every check with how often it agrees and where it stands

    Given the consistency topic's overview for Greece, in English or Greek
    When it is opened
    Then its heading is the topic's question
    And a summary gives the number of checks, of figures compared and agreeing, and how many checks found no inconsistency
    And there is one row per check in checks.json, those with differences first, each group in file order
    And each row gives "N of M match" and the check's status, and links to the check's page
    """
    r = _results()
    site.open(M5.format(lang=lang))
    assert site.find("h1").text.strip() == t(lang, "topic.official-figures-consistency.question")
    clean = [c for c in r["checks"] if c["agree"] == c["compared"]]
    summary = site.find('[data-m5="summary"]').text
    assert t(lang, "m5.summary", checks=len(r["checks"]), compared=num(lang, sum(c["compared"] for c in r["checks"]), 0),
             agree=num(lang, sum(c["agree"] for c in r["checks"]), 0)) in summary
    assert t(lang, "m5.summary.consistent", n=len(clean)) in summary
    order = [c for c in r["checks"] if c["agree"] < c["compared"]] + clean
    rows = site.all('[data-m5="checks"] tbody tr')
    assert len(rows) == len(r["checks"])
    for row, c in zip(rows, order):
        link = row.find_element("css selector", "th a")
        assert link.text.strip() == t(lang, f"m5.check.{c['id']}.title")
        assert link.get_attribute("href").endswith(M5.format(lang=lang) + f"checks/{c['id'][3:]}/")
        assert t(lang, "m5.count", agree=c["agree"], compared=c["compared"]) in row.text
        assert row.find_element("css selector", ".chip-status").text.strip() == t(lang, f"m5.status.{_status(c)}")


def test_check_page_lists_differences_and_offers_csv(site, base_url):
    """SEL-M5-002: a check's page lists each difference with its cause and offers every period as CSV

    Given the page of the check of the CPI's rates against its own index
    When it is opened and its download link is fetched
    Then it gives the check's count
    And its table of what was compared joins the years where all agree and sums to the count
    And its table has one row per difference, each with its cause
    And it links to the finding with its own page
    And it leads to the topic's section of the Data page, which lists the check's CSV
    And the CSV has a header and one row per period compared
    """
    c = next(x for x in _results()["checks"] if x["id"] == "gr-cpi-rates-own-index")
    site.open(M5.format(lang="en") + "checks/cpi-rates-own-index/")
    assert t("en", "m5.count", agree=c["agree"], compared=c["compared"]) in site.find('[data-m5="count"]').text
    rows = site.all('[data-m5="differences"] tbody tr')
    assert len(rows) == len(c["differences"])
    for row, d in zip(rows, c["differences"]):
        assert row.find_elements("css selector", "td")[-1].text.strip() == t("en", f"m5.cat.{d['explanation']}")
    compared = site.all('[data-m5="compared"] tbody tr')
    assert compared[0].find_element("css selector", "th").text.strip().startswith(min(c["by_year"]))
    assert sum(int("".join(ch for ch in r.find_elements("css selector", "td")[0].text if ch.isdigit())) for r in compared) == c["compared"]
    assert site.find('a.card[href$="/june-2001/"]').is_displayed()
    assert site.find('[data-m5="files"] a').get_attribute("href").endswith("/en/data/gr/#official-figures-consistency")
    path = f"{DATA}/downloads/gr-cpi-rates-own-index.csv"
    site.open("/en/data/gr/")
    assert len(site.all(f'[data-m5="files"] a[href="{path}"]')) == 1
    status, body = _get(base_url, path)
    lines = body.decode("utf-8").strip().split("\n")
    assert status == 200 and lines[0] == "period,published,rebuilt,difference,agree,explanation,finding"
    assert len(lines) - 1 == c["compared"]


def test_finding_page_links_back_and_lists_sources(site):
    """SEL-M5-003: a finding's page tells what happened, links back to its check and lists its sources

    Given the June 2001 finding's page, reached from its check
    When it is opened and its sources are unfolded
    Then its heading is the finding's title
    And it links back to the check's page
    And its sources list is not empty
    """
    site.open(M5.format(lang="en") + "checks/cpi-rates-own-index/")
    site.find('a.card[href$="/june-2001/"]').click()
    site.wait(lambda _: site.path.endswith("/checks/cpi-rates-own-index/june-2001/"), "the finding's page did not open")
    assert "June 2001" in site.find("h1").text
    back = next(a for a in site.all("header a") if a.text.strip() == t("en", "m5.check.gr-cpi-rates-own-index.title"))
    assert back.get_attribute("href").endswith(M5.format(lang="en") + "checks/cpi-rates-own-index/")
    summary = next(s for s in site.all("details.panel summary") if s.text.strip() == t("en", "m5.finding.sources"))
    summary.click()
    site.wait(lambda _: site.all("ol.sources li") and site.all("ol.sources li")[0].is_displayed(), "no sources shown")


def test_question_reached_from_groups_lines_up_sources(site):
    """SEL-M5-004: a question across sources lines up each source's value by year, reached from the Groups page

    Given the Groups page for Greece, whose two income limits are for the same year
    When its link to every year is followed
    Then the question's page opens
    And its table has a row per income year with both sources' poorest-fifth limits and the gap
    And the values match checks.json
    """
    q = next(x for x in _results()["questions"] if x["id"] == "gr-income-limits")
    site.open("/en/gr/inflation-by-group/groups/")
    site.find('[data-income-role="compare-link"] a').click()
    site.wait(lambda _: site.path.endswith("/same-question/income-limits/"), "the question's page did not open")
    assert site.find("h1").text.strip() == t("en", "m5.question.gr-income-limits.title")
    years = sorted({p.split("/")[0] for p in q["values"]["hbs"]
                    if q["values"]["hbs"].get(f"{p.split('/')[0]}/Q1") is not None
                    or q["values"]["silc"].get(f"{p.split('/')[0]}/Q1") is not None})
    rows = site.all('[data-m5="question"] tbody tr')
    assert len(rows) == len(years)
    last = years[-1]
    a, b = q["values"]["hbs"][f"{last}/Q1"], q["values"]["silc"][f"{last}/Q1"]
    cells = rows[-1].find_elements("css selector", "td")
    assert rows[-1].find_element("css selector", "th").text.strip() == last
    assert cells[0].text.strip() == ("–" if a is None else num("en", a, 0))
    assert cells[1].text.strip() == ("–" if b is None else num("en", b, 0))


def test_country_card_and_data_page_lead_to_topic(site, base_url):
    """SEL-M5-005: the home page's country card and the data page lead to the topic and its files

    Given the home page and Greece's data page
    When each is opened
    Then Greece's card links to the consistency topic
    And the data page has a section for the topic listing checks.json and each check's CSV
    And every file listed there answers with success
    """
    r = _results()
    site.open("/en/")
    assert site.find('[data-m5="card-link"] a').get_attribute("href").endswith(M5.format(lang="en"))
    site.open("/en/data/gr/")
    links = site.all('[data-m5="files"] a')
    assert len(links) == 2 + len(r["checks"]) + len(r["questions"])
    for a in links:
        href = a.get_attribute("href")
        assert _get(base_url, href[href.index("/data/"):])[0] == 200, href


def test_question_across_sources_lists_values_definitions_and_aade_as_published(site):
    """SEL-M5-006: a question across several sources gives each source's value by year, its definition, and AADE's figures as published

    Given the rent-paid question's page for Greece
    When it is opened
    Then its table has one column per source and one row per year in checks.json, values in billions of euros
    And pointing at each source's name in the table's header opens what it counts
    And AADE's figures are also given exactly as published, one row a year
    And the notice of each publisher whose terms ask for one (AADE, the European Commission) is shown, and no other
    """
    q = next(x for x in _results()["questions"] if x["id"] == "gr-rent-paid")
    site.open(M5.format(lang="en") + "same-question/rent-paid/")
    assert site.find("h1").text.strip() == t("en", "m5.question.gr-rent-paid.title")
    assert len(site.all('[data-m5="question"] thead th')) == 1 + len(q["sources"])
    periods = sorted({p for s in q["sources"] for p in q["values"][s["label"]]})
    rows = site.all('[data-m5="question"] tbody tr')
    assert len(rows) == len(periods)
    na = [s["label"] for s in q["sources"]].index("national_accounts")
    v = q["values"]["national_accounts"].get(periods[0])
    assert rows[0].find_elements("css selector", "td")[na].text.strip() == ("–" if v is None else num("en", v / 1e9, 2))
    for src in q["sources"]:
        term = site.find(f'[data-m5="question"] th[data-m5-source="{src["label"]}"] button.term')
        assert term.text.strip() == t("en", f"m5.src.gr-rent-paid.{src['label']}")
    first = q["sources"][0]["label"]
    # With a mouse, pointing opens it (a click follows its link to the source).
    ActionChains(site.driver).move_to_element(site.find(f'th[data-m5-source="{first}"] button.term')).perform()
    pop = site.find(f'th[data-m5-source="{first}"] .term-popover')
    site.wait(lambda _: pop.is_displayed(), "the definition did not open")
    assert t("en", f"m5.def.gr-rent-paid.{first}") in pop.text
    aade = [(p, x) for p, x in q["values"]["aade"].items() if x is not None]
    rows_published = site.all('[data-m5="as-published"] tbody tr')
    assert len(rows_published) == len(aade)
    assert rows_published[0].find_element("css selector", "td").text.strip() == num("en", aade[0][1], 2)
    notices = [p for p in ("aade", "ec-empl") if any(s["source"].startswith(f"{p}:") for s in q["sources"])]
    assert "aade" in notices
    assert [n.text.strip() for n in site.all('[data-m5="notice"]')] == [t("en", f"m5.notice.{p}") for p in notices]


def test_question_chart_draws_every_value_without_joining_years_apart(site):
    """SEL-M5-007: a question's chart draws every source's values, to scale, without joining years apart

    Given the renters question's page for Greece
    When it is opened
    Then its chart has an accessible label naming the question and its unit
    And the legend lists every source in order
    And there is one dot per value in checks.json
    And a line joins only values of consecutive years
    """
    q = next(x for x in _results()["questions"] if x["id"] == "gr-renters")
    site.open(M5.format(lang="en") + "same-question/renters/")
    svg = site.find('[data-m5="chart"] svg')
    assert svg.get_attribute("aria-label") == f'{t("en", "m5.question.gr-renters.title")} ({t("en", "m5.unit.percent")})'
    legend = [li.text.strip() for li in site.all('[data-m5="chart"] .m5-legend li')]
    assert legend == [t("en", f"m5.src.gr-renters.{s['label']}") for s in q["sources"]]
    values = [v for s in q["sources"] for v in q["values"][s["label"]].values() if v is not None]
    assert len(site.all('[data-m5="chart"] circle')) == len(values)
    consecutive = 0
    for s in q["sources"]:
        ys = sorted(int(y) for y, v in q["values"][s["label"]].items() if v is not None)
        consecutive += any(b == a + 1 for a, b in zip(ys, ys[1:]))
    assert len(site.all('[data-m5="chart"] path')) == consecutive


def test_groups_page_leads_to_tenure_and_household_type_pages(site):
    """SEL-M5-008: the Groups page leads from tenure and household types to their pages in the consistency topic

    Given the Groups page for Greece, and checks.json with the renters and rent-weight questions and the household-types check
    When it is opened and the household-types link is followed
    Then the tenure section links to the renters and the rent-weight questions
    And the household-types section links to the household-types check
    And following that link opens the check's page
    """
    r = _results()
    assert {"gr-renters", "gr-rent-weight", "gr-hbs-household-types"} <= {x["id"] for x in r["checks"] + r["questions"]}
    site.open("/en/gr/inflation-by-group/groups/")
    for qid in ("renters", "rent-weight"):
        href = site.find(f'#tenure [data-m5-link="{qid}"] a').get_attribute("href")
        assert href.endswith(M5.format(lang="en") + f"same-question/{qid}/")
    types = site.find('#household [data-m5-link="hbs-household-types"] a')
    assert types.text.strip() == f'{t("en", "m5.link.hbs-household-types")} →'
    types.click()
    site.wait(lambda _: site.path.endswith("/checks/hbs-household-types/"), "the check's page did not open")
    assert site.find("h1").text.strip() == t("en", "m5.check.gr-hbs-household-types.title")


def test_check_with_unknown_causes_says_what_is_open(site):
    """SEL-M5-009: a check whose causes aren't all known says what is open, where it is written up, and asks for ideas

    Given the spending table check, whose differences have no known cause and link to a finding
    When it is opened
    Then a section says how many differences have no known cause yet
    And it links to the finding that says what was looked at
    And it invites ideas by email to the project's support address
    """
    c = next(x for x in _results()["checks"] if x["id"] == "gr-hbs-spending")
    site.open(M5.format(lang="en") + "checks/hbs-spending/")
    block = site.find('[data-m5="open"]')
    assert t("en", "m5.open.count", n=c["differ"]["not-known"]) in block.text
    assert len(block.find_elements("css selector", 'a[href$="/checks/hbs-spending/survey-weights/"]')) == 1
    assert len(block.find_elements("css selector", 'a[href="mailto:support@traceconomics.com"]')) == 1
