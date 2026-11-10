"""The European Commission's labour market policy (LMP) database, run by DG EMPL.

One table: the people registered with each country's public employment service (`lmp_rjru`),
annual average stock, by registration status (registered unemployed by the national definition,
long-term, other jobseekers), age and sex. The consistency topic puts it beside the labour force
survey's unemployment: the same question ("how many are unemployed?") answered by a register and
by a survey. The national service's own files (Greece: DYPA) can't be republished; this copy can,
under the Commission's reuse policy.

DG EMPL serves the same API as Eurostat, so the file is fetched the same way: in full, only when
its "last data update" changed. Its key dimensions are written in capitals; the parser compares
them without regard to case.
"""

from __future__ import annotations

from traceconomics.sources import eurostat
from traceconomics.sources.base import RunContext

SOURCE = "ec-empl"
API = "https://webgate.ec.europa.eu/empl/redisstat/api/dissemination"
LIVE = ("lmp_rjru",)


def run(ctx: RunContext) -> None:
    for dataset in LIVE:
        eurostat.check_and_fetch(ctx, dataset, source=SOURCE, api=API, agency="EMPL")
