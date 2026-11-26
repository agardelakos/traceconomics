# Price index methods

How the engine turns item price indices and weights into an index, and how it is checked against
the official one. This page is for contributors and reviewers: what is computed, where, and what
proves it. The economics, for readers, is on the site's method pages
([inflation by household](https://traceconomics.com/en/gr/inflation-by-group/method/)).

The engine (`src/traceconomics/engine/`) does arithmetic only: it makes no method choices. The
topic code decides what to feed it (which weights, which index prices which item) and the engine
says nothing about why.

## Chain-linking at December

Each year has fixed weights, and each year is computed relative to December of the year before,
the link month. The years are then multiplied together (`engine/chain.py`):

<!-- from: traceconomics.engine.chain -->

```text
link(y, m)  = sum_i w_i * P_i(y, m) / P_i(Dec y-1)  /  sum_i w_i
I(y, m)     = I(Dec y-1) * link(y, m)
```

This is how the HICP (HICP Methodological Manual 2024, section 2.4) and the Greek CPI are built,
which is what makes the official indices rebuildable from their parts.

- **Any base works.** Only ratios within one item's own series are used, so 2015=100 and 2020=100
  series mix freely.
- **Each year keeps its own copy of December.** ELSTAT publishes one file a year; the file for year
  y holds December of y-1 as its link month, and the same December also appears in the previous
  year's file, not always with the same digits. So prices are passed per year, and each year links
  with the December printed in its own file (`module1/prices.py`). Ratios across several years are
  chained through each year's block, never taken between two blocks' levels.
- **Rates are computed as offices publish them** (`engine/rates.py`): from the published, rounded
  index, then rounded to one decimal (HICP manual, section 11.4.6). The engine returns them
  unrounded; code that must reproduce a published figure rounds the index first.

## The classification tree, and pricing with a parent's index

Codes are plain digits, and the tree is read from the codes themselves (`engine/tree.py`): `01`
food, `011` a group, `0111` a class, `01111` a subclass. A code's parent is the code with its last
digit removed; the parent of a division is all items. Codes that aren't digits (special aggregates
such as energy) are not part of the tree.

- **Leaves.** An index is built from the weighted codes with no weighted code below them. A parent
  whose children carry only part of its weight is not a leaf: the uncovered part is left out and
  the rest rescaled. (Pricing that remainder with the parent's index was tried on Greek data and
  matched the official index less well, because the parent's published weight is rounded.)
- **Parent fallback.** An item without its own index is priced with its nearest ancestor that has
  one, up to its division: the all-items index is never used, and an item with no index anywhere
  is left out and reported. Every fallback is recorded and reported (for example `07312 -> 0731: 36` months in V1-CPI's
  output), with the share of the weight priced in each month. Module 1 fails a run whose coverage
  falls below 100%, rather than quietly rescaling.
- **The topic decides, the engine searches.** The caller can map an item to the code whose index
  prices it (the search then climbs from there), or drop it from a year's basket. Module 1 uses
  this for tutoring (priced with secondary education, where its prices are collected) and imputed
  rent (priced with actual rents, the rental-equivalence approach); details in
  [Household group methods](Household-group-methods).

## The checks against official figures

Before the engine is used for anything else, it rebuilds Greece's official indices from the parts
their publishers release, in every release build (steps `check-v1` and `check-v1-cpi`):

- **V1** (`validate/v1.py`): the all-items HICP from Eurostat's sub-indices (`prc_hicp_minr`) and
  item weights (`prc_hicp_iw`), at four depths: divisions, groups and classes from 1997, and the
  finest published detail from 2015, when its weights start.
- **V1-CPI** (`validate/v1_cpi.py`): the Greek CPI from ELSTAT's table 07, which gives every item's
  monthly index and the year's weights. Checked strictly from 2014. In 2011 to 2013 the weights in
  the tables are identical (a fixed basket, not re-linked every December), and no linking rule
  reproduces those years from their re-issued tables, so they are reported, not checked.

### Why 0.1 points is the pass rule

The pass rule is the strictest one rebuilding can meet (`validate/compare.py`). Official annual
rates come from the published all-items index, rounded to two decimals. A rebuilt index comes from
sub-indices and weights that are themselves rounded, so it can land on the other side of a
rounding boundary: on Greek HICP data about one month in twenty is 0.1 points off, and none
further. So a month passes when:

- the rounded annual rates differ by at most 0.1 points, and
- the link to December, the part the engine computes, is within 0.001 of the official link.

The tolerance is never widened to hide a difference: a gap beyond it is reported and explained.

### What a tolerance can't catch

Two structural rules sit beside the tolerance, both found by replaying past Januaries from the
archive ([How a release goes live](How-a-release-goes-live)):

- **A repeated basket fails.** A year whose weights equal the year before's means the new year's
  basket wasn't read. Both publishers reweight every year (ELSTAT from 2014, Eurostat for Greece
  in every year since 1996), so this never happens with correct data. Last year's basket kept can
  miss the official link by as little as 1.0e-4, less than a correct January's 1.1e-4, so no
  tolerance separates the two.
- **A check behind the data fails.** If a check stops before the newest month the store holds, the
  newest months weren't checked. For the HICP the newest month is read from division `01`, which
  only a full release carries: Eurostat's flash adds a few headline aggregates for the next month
  weeks earlier.

Both are in `validate/compare.py` (`repeated_baskets`, `behind`) and pinned by PY-VONE-005 to PY-VONE-007,
PY-JAN-004 and PY-CLI-049 to PY-CLI-052.

## Where it is tested

- **Unit:** `tests/test_engine.py` pins the formulas on small made-up baskets: the leaves
  (PY-ENG-002), any base and any weight unit (PY-ENG-006, PY-ENG-007), the parent fallback and its
  limits (PY-ENG-008 to PY-ENG-010), linking across a weight change (PY-ENG-011), rates and rebasing
  (PY-ENG-014 to PY-ENG-016), each year's own December (PY-ENG-017) and the pricing map
  (PY-ENG-018, PY-ENG-019).
- **On real data:** V1 and V1-CPI run in every release build and fail it on a miss; their output
  lists every fallback and the coverage.
- **January:** a synthetic two-year CPI with a basket change (PY-JAN-001 to PY-JAN-004) passes the checks
  on a correct January and fails them with the link at the wrong month or last year's weights kept.

---

_This page is kept in the repository, in [`wiki/Price-index-methods.md`](https://github.com/agardelakos/traceconomics/blob/main/wiki/Price-index-methods.md), and copied here automatically. Changes go through a pull request; an edit made here is replaced at the next update._
