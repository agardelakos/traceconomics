---
title: "Income groups"
summary: "How people are ranked into income fifths. Default: people ranked by equivalised income."
order: 1
option: "grouping"
sources: [eurostat-equivalence-scale, kepe-2024, elstat-hbs-puf, elstat-hbs-2025-instructions, elstat-hbs-2025-questionnaire, elstat-hbs-2025-codes, eurostat-ilc-di01, eurostat-silc-guidelines-2024]
---
## The default: people, by equivalised income

People are ranked by their household's money income after taxes, divided by the modified OECD scale (1 for the first adult, 0.5 for each other person aged 14 or over, 0.3 for each child). Each fifth holds the same number of people. This is how Eurostat ranks income, and how KEPE's Greek study ranks it.

## Which income, and how it differs from Eurostat's

The income is the one ELSTAT's household budget survey records: money income from all sources, after income tax. Income in kind and imputed rent are not in it. Eurostat's official income figures come from a different survey, EU-SILC, which takes a few more things off. None of this changes how inflation is computed; it explains why our income limits and Eurostat's are not the same.

- **The self-employed's insurance contributions stay in their income** in the household budget survey; EU-SILC takes them off. ELSTAT's 2025 interviewer instructions say the profits written down include the contributions to compulsory insurance funds. Greece has many self-employed, so this is the largest known difference, and the public files can't measure it. We checked the 2025 survey's instructions; earlier years' are not checked yet.
- **Employees' contributions are taken off in both.** The survey asks for take-home pay.
- **Property tax (mainly ENFIA) is taken off in EU-SILC only.**
- **Money paid regularly to other households** (support to a relative, alimony) is taken off in EU-SILC. In the household budget survey up to 2023 it was spending, not taken off income. From 2024 ELSTAT records it among income, which suggests it is now taken off, but its definition of income doesn't say so and the public files can't show it. Only ELSTAT could settle it. The effect is small either way: about 1 person in 20 lives in a household that pays such money, and in Eurostat's 2025 figures leaving it in would raise the poorest fifth's upper limit by at most 1.8%.
- **Insurance payouts** (home, health, travel) count as income in the household budget survey only.
- **The period differs.** EU-SILC asks about the calendar year before the survey; the household budget survey asks about the last 1 to 12 months before each interview, spread over the survey year. So our survey of a year is compared with Eurostat's of the next year.

Together, property tax and money paid to other households move Eurostat's limits by about 4% (the poorest fifth's: €7 110 to €7 389, survey 2025). The self-employed's contributions and insurance payouts push the household budget survey's income higher still; its older income period pulls it down a little.

## The alternatives

- **Households, by total income.** Households, not people, ranked by their money income after taxes, without adjusting for household size.
- **People, by equivalised spending.** People ranked by their household's total spending per adult equivalent, as in ELSTAT's own survey press release. It counts all spending, including imputed rent, whichever spending concept the basket uses, so switching the concept never changes who is in a group.

## How much it matters

In September 2026 the poorest fifth's annual rate was 5.0% by default, 5.4% with households ranked by total income and 5.7% with people ranked by spending. The groupings sort different people into the "poorest" fifth, so their baskets differ.

The tenure, pensioner and all-households groups don't depend on this option.
