"""Consistency of official figures: do the official figures add up?

Each check takes two published sides of one figure (a rate and the index it comes from, a
rebuilt index and the published one, two surveys answering one question), compares them
period by period and keeps every comparison, not just a pass or fail. A difference is never
called an error: the code finds where the two sides differ and labels the differences it can
explain by itself (rounding); every other explanation is written by hand, with its evidence,
in `data/m5_explanations.toml`. Until one is written a difference reads "not known yet".

Nothing here fails a build because figures differ: showing the differences is the point.
Only a broken or unexpected input stops a run, through `checks.FormatError`.
"""
