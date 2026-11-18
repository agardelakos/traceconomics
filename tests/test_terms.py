"""The reuse-terms watch: only a change to the terms themselves raises an alert."""

import pytest

from traceconomics import htmltext
from traceconomics.sources import terms

pytestmark = pytest.mark.unit

EUROSTAT_BLOCK = "journal-content-article"
# Saved copies of the watched pages, by (source, dataset).
SAVED = {
    ("eurostat", "terms-copyright"): "eurostat_copyright_notice_2026-11-18.html",
    ("ec-empl", "terms-legal-notice"): "ec_legal_notice.html",
    ("elstat", "terms-reuse"): "elstat_terms_reuse.html",
}


def block_of(source, dataset):
    return next(p[4] for p in terms.PAGES if p[:2] == (source, dataset))


def test_a_banner_and_a_menu_label_are_not_a_change_of_terms(fixture_bytes):
    """PY-TERMS-001: a maintenance banner and a renamed menu label don't count as changed terms

    Given Eurostat's copyright notice as served on 2026-11-07, with a maintenance warning banner
    And the same page as served on 2026-11-18, without the banner and with a menu item renamed
    When the two copies are compared
    Then the banner and the new label are in the visible text of only one copy each
    And the terms block reads the same in both, so the verdict is "same"
    """
    old = fixture_bytes("eurostat_copyright_notice_2026-11-07.html")
    new = fixture_bytes("eurostat_copyright_notice_2026-11-18.html")
    banner = "will be temporarily unavailable"
    assert banner in htmltext.visible_text(old) and banner not in htmltext.visible_text(new)
    assert "Statistics under development" in htmltext.visible_text(new)
    assert "Statistics under development" not in htmltext.visible_text(old)
    assert terms.compare(old, new, EUROSTAT_BLOCK) == "same"


def test_a_changed_word_of_the_terms_is_a_change(fixture_bytes):
    """PY-TERMS-002: one changed word inside the terms is a change

    Given Eurostat's copyright notice as served on 2026-11-18
    And a copy in which "non-commercial" in the terms reads "personal"
    When the two copies are compared
    Then the verdict is "changed"
    """
    old = fixture_bytes("eurostat_copyright_notice_2026-11-18.html")
    new = old.replace(b"for commercial or non-commercial purposes", b"for commercial or personal purposes", 1)
    assert new != old
    assert terms.compare(old, new, EUROSTAT_BLOCK) == "changed"


def test_a_page_without_its_terms_block_is_reported_as_missing(fixture_bytes):
    """PY-TERMS-003: a new copy without the terms block is "missing", never compared as a whole page

    Given Eurostat's copyright notice as served on 2026-11-18
    And a copy whose article element lost the class that marks the terms block
    When the two copies are compared
    Then the verdict is "missing"
    """
    old = fixture_bytes("eurostat_copyright_notice_2026-11-18.html")
    new = old.replace(b'class="journal-content-article ', b'class="article-body ')
    assert new.count(b"journal-content-article") < old.count(b"journal-content-article")
    assert htmltext.block_text(new, EUROSTAT_BLOCK) is None
    assert terms.compare(old, new, EUROSTAT_BLOCK) == "missing"


def test_an_old_copy_without_the_block_cannot_vouch_for_the_new_one(fixture_bytes):
    """PY-TERMS-004: when only the old copy lacks the terms block, the verdict is "changed"

    Given a copy of Eurostat's copyright notice whose article element lacks the block's class
    And the page as served on 2026-11-18, with the block
    When the old copy is compared with the new one
    Then the verdict is "changed"
    """
    new = fixture_bytes("eurostat_copyright_notice_2026-11-18.html")
    old = new.replace(b'class="journal-content-article ', b'class="article-body ')
    assert terms.compare(old, new, EUROSTAT_BLOCK) == "changed"


def test_a_new_address_for_the_policy_document_is_a_change(fixture_bytes):
    """PY-TERMS-005: a new link target inside the terms block is a change, even with the same words

    Given ELSTAT's reuse page, whose terms block links to the reuse policy PDF
    And a copy in which the PDF's address carries a new version stamp
    When the two copies are compared
    Then the visible text is the same
    And the verdict is "changed"
    """
    block = block_of("elstat", "terms-reuse")
    old = fixture_bytes("elstat_terms_reuse.html")
    new = old.replace(b"?t=1464603016196", b"?t=1800000000000")
    assert new != old
    assert htmltext.visible_text(new) == htmltext.visible_text(old)
    assert terms.compare(old, new, block) == "changed"


@pytest.mark.parametrize(
    ("page", "phrase"),
    [
        (("eurostat", "terms-copyright"), "Creative Commons Attribution 4.0 International licence"),
        (("ec-empl", "terms-legal-notice"), "Creative Commons Attribution 4.0 International (CC BY 4.0) licence"),
        (("elstat", "terms-reuse"), "Copyright_Reuse_Policy_EN.pdf"),
    ],
)
def test_each_watched_page_has_its_terms_block(fixture_bytes, page, phrase):
    """PY-TERMS-006: each watched page's saved copy has a terms block holding its terms

    Given a saved copy of each watched HTML page (Eurostat, the Commission, ELSTAT)
    When the block named for that page in the watch list is read
    Then it is found
    And it holds the page's licence or the address of its policy document
    And it leaves out the site's menus
    """
    text = htmltext.block_text(fixture_bytes(SAVED[page]), block_of(*page))
    assert text is not None
    assert phrase in text
    assert "Skip to" not in text and "Statistics under development" not in text


def test_a_file_without_a_block_counts_any_stored_change():
    """PY-TERMS-007: without a block (a PDF), or without the new bytes, every stored change counts

    Given two different PDF files
    When they are compared without a block
    And an HTML page is compared with no new bytes to read
    Then both verdicts are "changed"
    """
    assert terms.compare(b"%PDF one", b"%PDF two", None) == "changed"
    assert terms.compare(b"<p>a</p>", None, EUROSTAT_BLOCK) == "changed"


def test_block_text_reads_only_the_marked_elements():
    """PY-TERMS-008: block text keeps the marked elements' text and links, and nothing else

    Given a page with text before, a marked element holding unclosed paragraphs, a script and a link,
    And a second marked element after unmarked text
    When the block text is read for that class
    Then it holds the two blocks' text and the link target, one line each, in page order
    And neither the script nor the unmarked text
    And a class that no element carries gives None
    """
    page = (
        "<p>menu</p><div class='terms main'><p>one<p>two <a href='/policy.pdf'>policy</a>"
        "<script>var x</script></div><p>banner</p><section class=terms>three</section>"
    )
    assert htmltext.block_text(page, "terms") == "one\ntwo\n[a: /policy.pdf]\npolicy\nthree"
    assert htmltext.block_text(page, "absent") is None
