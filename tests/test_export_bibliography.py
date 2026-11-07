"""The bibliography as plain data for the website."""

from traceconomics import references
from traceconomics.export import bibliography

SAMPLE = r"""
@report{some-report,
  author       = {{Hellenic Statistical Authority (ELSTAT)}},
  title        = {User oriented quality report (January 2026 -- )},
  type         = {Quality report},
  number       = {document 594835},
  url          = {https://example.org/a_b?x=1&y=2},
}

@dataset{some-data,
  author       = {{Eurostat}},
  title        = {Prices \& weights: {HICP} ECOICOP\_2},
  number       = {PRC\_HICP\_MINR},
  date         = {2026},
}
"""


def test_fields_are_read_with_nested_braces_and_latex_taken_off():
    """PY-BIBEXP-001: fields are read through nested braces with LaTeX markup removed

    Given a BibTeX sample with braced authors, escaped characters, a "--" dash and a URL with "_" and "&"
    When it is parsed for the website
    Then the entry type and every field are read in full
    And the outer braces, escapes and braces around words are removed, and "--" becomes an en dash
    And the URL is kept exactly as written
    """
    e = bibliography.parse(SAMPLE)
    r = e["some-report"]
    assert r["entrytype"] == "report" and r["type"] == "Quality report"
    assert r["author"] == "Hellenic Statistical Authority (ELSTAT)"
    assert r["title"] == "User oriented quality report (January 2026 – )"
    assert r["url"] == "https://example.org/a_b?x=1&y=2"                  # addresses are kept as they are
    d = e["some-data"]
    assert d["title"] == "Prices & weights: HICP ECOICOP_2" and d["number"] == "PRC_HICP_MINR"


def test_the_real_bibliography_parses_completely():
    """PY-BIBEXP-002: the project's bibliography parses completely

    Given the project's own bibliography
    When it is parsed for the website
    Then it yields exactly the entries the references module knows
    And every entry has an author and a title
    """
    e = bibliography.parse(references.text())
    assert set(e) == set(references.entries())
    for key, fields in e.items():
        assert fields.get("author") and fields.get("title"), key
