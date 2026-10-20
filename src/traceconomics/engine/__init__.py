"""The aggregation engine: weights and item price indices in, an aggregate index out.

It knows nothing about sources, groups of households or method options. It
takes one set of weights per year and price indices per item, and builds an
annually chain-linked index the way the HICP and the Greek CPI are built:
each year is linked at December of the previous year.
"""

from traceconomics.engine.chain import ChainResult, chain
from traceconomics.engine.rates import annual_average_rate, annual_rate, monthly_rate, rebase

__all__ = ["ChainResult", "chain", "annual_rate", "monthly_rate", "annual_average_rate", "rebase"]
