---
title: "Weights timing"
summary: "Which year's survey a year's weights come from. Default: rule N, the year before, revised once."
order: 5
option: "weights_timing"
sources: [reg-2020-1148, reg-2016-792, kepe-2024, kepe-2025]
---
## The default: rule N

The law asks consumer price index weights to represent the year before. Rule N does that: a year's final weights come from the survey of the year before. That survey's microdata appear about sixteen months into the year, so until then a first estimate uses the newest survey available, and the year is revised once. In the pandemic years this gives what Eurostat and ELSTAT did: 2021 from the 2020 survey, 2023 from the 2022 survey.

## The alternatives

- **Rule F: fixed, never revised.** The weights are set when the year begins and never change. Before our archive existed, the survey files' release dates can't be used (the files for 2008–2017 carry dates from late 2018 or after), so for past years Rule F uses the survey of three years before, today's lag. That is our choice. It starts in 2011, because there is no survey before 2008. Its 2023 weights come from the 2020 lockdown survey, the case Eurostat warned against.
- **Rule U: the same year.** A year uses its own survey, as KEPE's study does. Its weights don't come from before the prices, so it isn't a Laspeyres-type index; it is shown to compare with studies made after the fact. It stops at the newest survey (2024).

## How much it matters

The 2022 gap between the poorest and richest fifth is 1.8 points under rule N, 1.4 under rule U and 1.1 under rule F, whose weights come from 2019, before food and energy took a larger share of poorer households' spending. Single years can differ by up to 0.7 points between rules, which is why the choice is explained, not hidden.
