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
    return ("agree" if differ == c["differ"].get("rounding", 0) else "explained" if unknown == 0
            else "partly" if unknown < differ else "unknown")


def _get(base_url: str, path: str) -> tuple[int, bytes]:
    with urllib.request.urlopen(base_url + path, timeout=30) as r:
        return r.status, r.read()


ORDER = ["explained", "partly", "unknown", "agree"]


def _by_status(checks: list[dict]) -> list[dict]:
    return [c for st in ORDER for c in checks if _status(c) == st]


@pytest.mark.parametrize("lang", ["en", "el"])
def test_overview_gives_numbers_and_check_cards(site, lang):
    """SEL-M5-001: the overview gives three numbers and every check as a card, explained first

    Given the consistency topic's overview for Greece, in English or Greek
    When it is opened
    Then its heading is the topic's question
    And it gives the number of checks, the figures compared with the years they span, and the share that agree, rounded down
    And there is one card per check in checks.json: explained first, then partly explained, reason not known yet, consistent, each group in file order
    And each card asks its question in plain words, linking to the check's page, with its status, "N of M match" and the years actually checked
    And a consistent card whose other figures differ only by rounding says how many, in a note
    """
    r = _results()
    site.open(M5.format(lang=lang))
    assert site.find("h1").text.strip() == t(lang, "topic.official-figures-consistency.question")
    compared, agree = sum(c["compared"] for c in r["checks"]), sum(c["agree"] for c in r["checks"])
    years = sorted(y for c in r["checks"] for y in c["by_year"])
    stats = site.all('[data-m5="stats"] p')
    assert stats[0].find_element("css selector", "strong").text.strip() == num(lang, len(r["checks"]), 0)
    assert stats[1].find_element("css selector", "strong").text.strip() == num(lang, compared, 0)
    assert t(lang, "m5.stat.compared", **{"from": years[0], "to": years[-1]}) in stats[1].text
    assert stats[2].find_element("css selector", "strong").text.strip() == f"{agree * 100 // compared}%"
    cards = site.all('[data-m5="checks"] [data-m5-card]')
    assert len(cards) == len(r["checks"])
    for card, c in zip(cards, _by_status(r["checks"])):
        assert card.get_attribute("data-m5-card") == c["id"]
        link = card.find_element("css selector", "a.title")
        assert link.text.replace("\xa0", " ").strip() == t(lang, f"m5.check.{c['id']}.question") + " →"
        assert link.get_attribute("href").endswith(M5.format(lang=lang) + f"checks/{c['id'][3:]}/")
        assert card.find_element("css selector", ".chip-status").text.strip() == t(lang, f"m5.status.{_status(c)}")
        assert card.find_element("css selector", '[data-m5="count"]').text.strip() == t(
            lang, "m5.count", agree=num(lang, c["agree"], 0), compared=num(lang, c["compared"], 0))
        span = sorted(c["by_year"])
        assert t(lang, "m5.checked", **{"from": span[0], "to": span[-1]}) in card.text
        rounding = c["compared"] - c["agree"] if _status(c) == "agree" else 0
        notes = card.find_elements("css selector", '[data-m5="note"]')
        assert [n.text.strip() for n in notes] == ([t(lang, "m5.note.rounding", n=num(lang, rounding, 0))] if rounding else [])
    assert any(_status(c) == "agree" and c["agree"] < c["compared"] for c in r["checks"])


def test_check_page_lists_differences_and_offers_csv(site, base_url):
    """SEL-M5-002: a check's page lists each difference with its cause and offers every period as CSV

    Given the page of the check of the CPI's rates against its own index
    When it is opened and its download link is fetched
    Then its heading is the check's question in plain words, with its technical name under it
    And it gives the check's count
    And its table of what was compared joins the years where all agree and sums to the count
    And its table has one row per difference, each with its cause
    And it links to the finding with its own page
    And it leads to the topic's section of the Data page, which lists the check's CSV
    And the CSV has a header and one row per period compared
    """
    c = next(x for x in _results()["checks"] if x["id"] == "gr-cpi-rates-own-index")
    site.open(M5.format(lang="en") + "checks/cpi-rates-own-index/")
    assert site.find("h1").text.strip() == t("en", "m5.check.gr-cpi-rates-own-index.question")
    assert site.find('[data-m5="technical"]').text.strip() == t("en", "m5.check.gr-cpi-rates-own-index.title")
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
    back = next(a for a in site.all("header a") if a.text.strip() == t("en", "m5.check.gr-cpi-rates-own-index.question"))
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
    assert site.find("h1").text.strip() == t("en", "m5.check.gr-hbs-household-types.question")


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


def test_questions_page_gives_cards_with_teasers_and_source_chips(site):
    """SEL-M5-010: the questions page gives each question as a card: its title, a short teaser and a chip per source

    Given the "Same question, different sources" page for Greece and the questions in checks.json
    When it is opened
    Then there is one card per question, each linking to its page with its title and teaser
    And each card has a chip per kind of source, none repeated, the rent-paid card naming tax returns (AADE) and the national accounts (Eurostat)
    """
    r = _results()
    site.open(M5.format(lang="en") + "same-question/")
    cards = site.all('[data-m5="questions"] a.card')
    assert len(cards) == len(r["questions"])
    for card, q in zip(cards, r["questions"]):
        assert card.get_attribute("href").endswith(M5.format(lang="en") + f"same-question/{q['id'][3:]}/")
        assert card.find_element("css selector", ".title").text.strip() == t("en", f"m5.question.{q['id']}.title") + " →"
        assert card.find_element("css selector", ".text").text.strip() == t("en", f"m5.question.{q['id']}.teaser")
        names = [c.text.strip() for c in card.find_elements("css selector", ".source-chip")]
        assert names and len(set(names)) == len(names)
        if q["id"] == "gr-rent-paid":
            assert t("en", "m5.chip.tax-aade") in names and t("en", "m5.chip.na-eurostat") in names


def test_section_strip_lists_pages_and_marks_the_current_one(site):
    """SEL-M5-011: inside a section, the bar's third row lists the section's pages by short name and marks the one being read

    Given a check's page, a finding of that check, and a question's page, with the checks and questions in checks.json
    When each is opened
    Then on the check's page the row lists every check in the overview's order, the check being read as plain text marked current and the others as links to their pages
    And the Checks tab is marked as the current section, not the current page
    And on the finding's page the same row marks its check as current
    And on the question's page the row lists every question, that question marked current
    """
    r = _results()
    order = _by_status(r["checks"])

    def row(items, kind, current):
        assert [li.text.strip() for li in site.all("nav[data-strip] li")] == [t("en", f"m5.short.{x['id']}") for x in items]
        assert site.find('nav[data-strip] [aria-current="page"]').text.strip() == t("en", f"m5.short.{current}")
        links = {a.text.strip(): a.get_attribute("href") for a in site.all("nav[data-strip] a")}
        for x in items:
            if x["id"] != current:
                assert links[t("en", f"m5.short.{x['id']}")].endswith(M5.format(lang="en") + f"{kind}/{x['id'][3:]}/")

    site.open(M5.format(lang="en") + "checks/cpi-rates-own-index/")
    row(order, "checks", "gr-cpi-rates-own-index")
    tab = next(a for a in site.all(".topic-nav.sub a") if a.text.strip() == t("en", "nav.checks"))
    assert tab.get_attribute("aria-current") == "true"
    site.open(M5.format(lang="en") + "checks/cpi-rates-own-index/june-2001/")
    assert site.find('nav[data-strip] [aria-current="page"]').text.strip() == t("en", "m5.short.gr-cpi-rates-own-index")
    site.open(M5.format(lang="en") + "same-question/renters/")
    row(r["questions"], "same-question", "gr-renters")


@pytest.mark.phone
def test_section_strip_opens_scrolled_to_the_current_page_on_a_phone(phone):
    """SEL-M5-012: on a phone, the bar's third row opens scrolled to the page being read

    Given a phone-sized screen
    And a question's page whose row of questions is wider than the screen, the question being read far along it
    When it is opened
    Then the row is wider than the screen
    And the question being read is wholly inside the row's visible part
    """
    phone.open(M5.format(lang="en") + "same-question/renters/")
    row = phone.find("nav[data-strip] ul")
    box = phone.driver.execute_script(
        "const r = arguments[0].getBoundingClientRect(); return {scroll: arguments[0].scrollWidth, client: arguments[0].clientWidth, left: r.left};", row)
    assert box["scroll"] > box["client"]
    item = phone.driver.execute_script("const r = arguments[0].getBoundingClientRect(); return {x: r.left, w: r.width};",
                                       phone.find('nav[data-strip] [aria-current="page"]'))
    assert box["left"] - 1 <= item["x"] and item["x"] + item["w"] <= box["left"] + box["client"] + 1


def test_status_chips_have_their_own_colours(site):
    """SEL-M5-013: each status's chip has its own colour, and a consistent check's chip carries a tick

    Given the consistency topic's overview, with consistent, explained and unexplained checks
    When it is opened
    Then chips of different statuses have different background colours
    And the Consistent chip is drawn with a tick that is not part of its text
    """
    site.open(M5.format(lang="en"))
    chips = site.driver.execute_script("""
        return [...document.querySelectorAll('[data-m5="checks"] .chip-status')].map((el) => ({
          status: [...el.classList].find((c) => c !== 'chip-status'), background: getComputedStyle(el).backgroundColor,
          tick: getComputedStyle(el, '::before').content }));""")
    by_status = {c["status"]: c["background"] for c in chips}
    assert {"agree", "explained"} <= set(by_status)
    assert len(set(by_status.values())) == len(by_status)
    assert "✓" in next(c for c in chips if c["status"] == "agree")["tick"]
    assert site.find('[data-m5="checks"] .chip-status.agree').text.strip() == t("en", "m5.status.agree")


def test_status_buttons_show_one_status_at_a_time(site):
    """SEL-M5-014: the overview's status buttons show one status's checks at a time

    Given the consistency topic's overview, with explained, unexplained and consistent checks and none partly explained
    When the Explained button is pressed
    And it is pressed again
    Then at first every card shows, All is pressed, and there is a button only for each status some check has, with its count
    And after the first press only the explained cards and the key's explained line show, and the count shown is announced
    And after the second press every card shows again and All is pressed
    """
    r = _results()
    n = {st: sum(_status(c) == st for c in r["checks"]) for st in ORDER}
    site.open(M5.format(lang="en"))
    buttons = site.all('[data-m5="filter"] button')
    assert [b.text.strip() for b in buttons] == [t("en", "m5.filter.count", label=t("en", "m5.filter.all"), n=len(r["checks"]))] + [
        t("en", "m5.filter.count", label=t("en", f"m5.status.{st}"), n=n[st]) for st in ORDER if n[st]]
    assert site.find('[data-m5="filter"] button[data-filter="all"]').get_attribute("aria-pressed") == "true"
    shown = lambda: [c for c in site.all('[data-m5="checks"] [data-m5-card]') if c.is_displayed()]
    assert len(shown()) == len(r["checks"])
    explained = site.find('[data-m5="filter"] button[data-filter="explained"]')
    explained.click()
    site.wait(lambda _: explained.get_attribute("aria-pressed") == "true", "the button was not pressed")
    assert len(shown()) == n["explained"] and all(c.get_attribute("data-status") == "explained" for c in shown())
    assert len([k for k in site.all('[data-m5="key"] [data-key]') if k.is_displayed()]) == 1
    assert site.find('[data-m5="shown"]').get_attribute("textContent") == t("en", "m5.filter.shown", n=n["explained"], total=len(r["checks"]))
    explained.click()
    site.wait(lambda _: len(shown()) == len(r["checks"]), "the cards did not all come back")
    assert site.find('[data-m5="filter"] button[data-filter="all"]').get_attribute("aria-pressed") == "true"


def test_checks_page_compares_every_check_in_a_table(site):
    """SEL-M5-015: the Checks page compares every check in one table, in the overview's order

    Given the Checks page for Greece and the checks in checks.json
    When it is opened
    Then its table has a row per check in the overview's order
    And each row asks the check's question, linking to its page, with its count and status
    """
    r = _results()
    site.open(M5.format(lang="en") + "checks/")
    rows = site.all('[data-m5="check-list"] tbody tr')
    assert len(rows) == len(r["checks"])
    for row, c in zip(rows, _by_status(r["checks"])):
        link = row.find_element("css selector", "th a")
        assert link.text.strip() == t("en", f"m5.check.{c['id']}.question")
        assert link.get_attribute("href").endswith(M5.format(lang="en") + f"checks/{c['id'][3:]}/")
        assert t("en", "m5.count", agree=num("en", c["agree"], 0), compared=num("en", c["compared"], 0)) in row.text
        assert row.find_element("css selector", ".chip-status").text.strip() == t("en", f"m5.status.{_status(c)}")
