---
title: "Income groups"
summary: "How people are ranked into income fifths. Default: people ranked by equivalised income."
order: 1
option: "grouping"
sources: [eurostat-equivalence-scale, kepe-2024, elstat-hbs-puf]
---
## The default: people, by equivalised income

People are ranked by their household's money income after taxes, divided by the modified OECD scale (1 for the first adult, 0.5 for each other person aged 14 or over, 0.3 for each child). Each fifth holds the same number of people. This is how Eurostat ranks income, and how KEPE's Greek study ranks it.

## The alternatives

- **Households, by total income.** Households, not people, ranked by their money income after taxes, without adjusting for household size.
- **People, by equivalised spending.** People ranked by their household's total spending per adult equivalent, as in ELSTAT's own survey press release. It counts all spending, including imputed rent, whichever spending concept the basket uses, so switching the concept never changes who is in a group.

## How much it matters

In September 2026 the poorest fifth's annual rate was 5.0% by default, 5.4% with households ranked by total income and 5.7% with people ranked by spending. The groupings sort different people into the "poorest" fifth, so their baskets differ.

The tenure, pensioner and all-households groups don't depend on this option.
