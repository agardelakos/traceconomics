"""The publishers' reuse terms, watched for changes.

Everything we publish relies on these terms, so a change must be read by a
person before the next release. A changed page raises an alert.
"""

from __future__ import annotations

from traceconomics import htmltext
from traceconomics.sources.base import RunContext

PAGES = (
    ("eurostat", "terms-copyright", "https://ec.europa.eu/eurostat/help/copyright-notice", ".html"),
    ("elstat", "terms-reuse", "https://www.statistics.gr/en/pneumatika-diakaiomata-kai-epanachresimopoiese-stoicheion", ".html"),
    ("elstat", "terms-reuse-pdf",
     "https://www.statistics.gr/documents/20181/1412250/Copyright_Reuse_Policy_EN.pdf/dfacb7d1-3d9b-471f-851a-8b8b09994a74",
     ".pdf"),
)


def run(ctx: RunContext) -> None:
    for source, dataset, url, ext in PAGES:
        first = ctx.archive.latest(source, dataset) is None
        content_of = htmltext.visible_text if ext == ".html" else None
        result, _ = ctx.fetch_and_store(source, dataset, url, ext=ext, content_of=content_of)
        if result and result.status == "stored" and not first:
            ctx.alerts.append(
                f"Reuse terms changed: {source} ({url}). Read the new version before the next release. "
                f"Saved copy: {result.path}"
            )
