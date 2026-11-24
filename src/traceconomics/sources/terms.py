"""The publishers' reuse terms, watched for changes.

Everything we publish relies on these terms, so a change must be read by a
person before the next release. The archive keeps every version of a page whose
visible text changed, as fetched. The alert compares only the block that holds the
terms: publishers' pages also carry menus and maintenance banners, and an alert
for every banner trains the reader to skip the one that matters. A change outside
the block is still reported, as a note.
"""

from __future__ import annotations

from traceconomics import htmltext
from traceconomics.sources.base import RunContext

# (source, dataset, url, extension, class of the element(s) holding the terms; None: the whole file)
PAGES = (
    # A Liferay page: the article body is the one "journal-content-article" element.
    (
        "eurostat",
        "terms-copyright",
        "https://ec.europa.eu/eurostat/help/copyright-notice",
        ".html",
        "journal-content-article",
    ),
    # The Commission's own legal notice: its reuse policy covers DG EMPL's LMP database.
    # The page body is the main column; the side column is the in-page menu.
    ("ec-empl", "terms-legal-notice", "https://commission.europa.eu/legal-notice_en", ".html", "ecl-col-l-9"),
    # AADE's terms aren't watched here: its CDN refuses cloud servers. They are read by hand
    # with each yearly import of its workbooks.
    (
        "elstat",
        "terms-reuse",
        "https://www.statistics.gr/en/pneumatika-diakaiomata-kai-epanachresimopoiese-stoicheion",
        ".html",
        # Two such elements: the terms (a link to the policy PDF, watched below) and the
        # footer's address. Both count; the address rarely changes.
        "journal-content-article",
    ),
    (
        "elstat",
        "terms-reuse-pdf",
        "https://www.statistics.gr/documents/20181/1412250/Copyright_Reuse_Policy_EN.pdf/dfacb7d1-3d9b-471f-851a-8b8b09994a74",
        ".pdf",
        None,
    ),
)


def run(ctx: RunContext) -> None:
    """Fetch every watched terms page; alert when a new copy's terms block changed or can't be found.

    A new copy whose terms block reads the same is reported as a note.
    """
    for source, dataset, url, ext, block in PAGES:
        previous = ctx.archive.latest(source, dataset)
        content_of = htmltext.visible_text if ext == ".html" else None
        result, data = ctx.fetch_and_store(source, dataset, url, ext=ext, content_of=content_of)
        if not (result and result.status == "stored" and previous):
            continue
        old = (ctx.archive.root / previous["path"]).read_bytes()
        verdict = compare(old, data, block)
        if verdict == "same":
            ctx.notes.append(
                f"Terms page changed outside the terms (menus, banners): {source} ({url}). "
                f"The terms block is word for word the same; nothing to read. Saved copy: {result.path}"
            )
        elif verdict == "missing":
            ctx.alerts.append(
                f"Reuse terms page changed and its terms block (class {block!r}) wasn't found: {source} ({url}). "
                f"The layout changed: read the page before the next release, then update the watch "
                f"(sources/terms.py). Saved copy: {result.path}"
            )
        else:
            ctx.alerts.append(
                f"Reuse terms changed: {source} ({url}). Read the new version before the next release. "
                f"Saved copy: {result.path}"
            )


def compare(old: bytes, new: bytes | None, block: str | None) -> str:
    """Whether the new copy's terms block is 'same', 'changed' or 'missing'.

    'same' when the terms block reads the same in both copies, 'changed' when it differs,
    'missing' when the new copy has no such block.

    Without a block (a PDF) or the new bytes (a file too big to hold), any stored change counts
    as 'changed'. An old copy without the block (the page before a layout change) can't
    vouch for the new one, so that is 'changed' too.
    """
    if block is None or new is None:
        return "changed"
    new_terms = htmltext.block_text(new, block)
    if new_terms is None:
        return "missing"
    return "same" if htmltext.block_text(old, block) == new_terms else "changed"
