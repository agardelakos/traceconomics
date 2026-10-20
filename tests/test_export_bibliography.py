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
    e = bibliography.parse(SAMPLE)
    r = e["some-report"]
    assert r["entrytype"] == "report" and r["type"] == "Quality report"
    assert r["author"] == "Hellenic Statistical Authority (ELSTAT)"
    assert r["title"] == "User oriented quality report (January 2026 – )"
    assert r["url"] == "https://example.org/a_b?x=1&y=2"                  # addresses are kept as they are
    d = e["some-data"]
    assert d["title"] == "Prices & weights: HICP ECOICOP_2" and d["number"] == "PRC_HICP_MINR"


def test_the_real_bibliography_parses_completely():
    e = bibliography.parse(references.text())
    assert set(e) == set(references.entries())
    for key, fields in e.items():
        assert fields.get("author") and fields.get("title"), key
