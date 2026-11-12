# Design principles

The rules the project keeps, each with its reason. The binding short form is in
[CONTRIBUTING.md](https://github.com/agardelakos/traceconomics/blob/main/CONTRIBUTING.md); this page
explains why.

## What we publish

**Produce numbers that don't otherwise exist.** The project is not a general dashboard that
re-displays official figures. Official headline figures appear only as context for our own
numbers, linked to their source. _Why:_ re-displaying what a statistics office already publishes
adds nothing; working out what nobody publishes does.

**Trace every number to the source.** Every published value goes back, through the store, to a
file in the raw archive, with its URL, fetch time and hash. _Why:_ statistics offices revise
numbers and overwrite files in place. Without a copy of each version, nobody can later check what
was known on a given date.

**Compute from the lowest level; keep the publisher's figure as a check.** We fetch the most
detailed data a publisher releases (item indices, weights, levels) and compute rates and
aggregates ourselves. The publisher's own aggregate is compared with ours, not copied. _Why:_ our
own series are built from those parts, so the engine must first prove it rebuilds the official
figures from them; a computed figure also carries full precision, where a published one is
rounded.

**Show differences; never tune them away.** Where our figure and an official one differ, the
difference is shown and explained. It never stops the build, and no method, tolerance or test is
adjusted to make it disappear. _Why:_ a tracker that quietly fits its numbers to the official ones
can't be trusted to find anything.

**Every number cites its method sources.** Each series, indicator and glossary entry points to the
paper or manual its method comes from, through one shared bibliography file. The build fails if a
published series has no source. Each method page lists where we differ from the sources, and our
own choices are labelled as ours. _Why:_ a number a reader can't trace to a method is a number they
have to take on trust.

**Options with defaults; headlines use the default.** Method choices are switches the reader can
change, each with a default and a plain explanation. Every combination is pre-computed, archived
and citable. Headlines always use the default; a chart drawn with other options names them, and a
shared link carries them in its address. Options that can't be computed for a country or period
are shown greyed, with the reason; options that will never be built are not shown. _Why:_
reasonable people choose differently on method; showing the effect of each choice is more honest
than hiding it, and a fixed default keeps headlines comparable.

**Honest uncertainty.** Survey-based figures carry error bands (bootstrap standard errors), small
cells are merged or flagged, and back-calculated history is flagged as such. Standard errors that
can't be computed are reported as unavailable, never invented.

## How we explain

**Plain explanations for everything.** Every term, series, option and chart gets a plain-language
explanation for the curious non-expert, in every language the site offers. Plain words come before
technical terms; explanations come in layers (one sentence, then more detail, then the method page).
_Why:_ the first audience is anyone curious about the economy; specialists still get the method
pages and downloads.

**Each country's language and English.** Every text is translatable, and every English change is
translated in the same change. A language is offered once a native speaker has reviewed it. _Why:_
the people a country's numbers are about should be able to read them.

**Neutral wording.** The site states what the numbers show and how they were made, without
political framing.

## How the pipeline behaves

**Fail loudly on format or terms changes.** A parser that meets a file it doesn't expect raises
`FormatError`; it never guesses. A change in a publisher's reuse terms raises an alert. _Why:_ a
changed layout silently misread produces numbers that look right and aren't.

**Polite fetching.** One request at a time with a pause, a User-Agent naming the project, retries
with growing waits, `robots.txt` respected, bulk files preferred, and a download only when the
publisher's update time changed. _Why:_ the project depends on public services it doesn't pay for;
it should cost them as little as possible.

**Raw files are never edited.** The archive keeps every file exactly as received, append-only.
Test fixtures that are untouched copies are stored byte for byte and checked against their hashes.
_Why:_ anyone can download the original again and compare hashes; an edited file proves nothing.

**Microdata are never published.** Survey microdata are read in memory on the maintainer's own
machines and never published, committed, synced or used in tests. Only aggregates leave, with small
cells merged so that no single cell can be shown or worked out by subtraction. _Why:_ the
publishers' terms and the households' privacy.

**Reproducible to the byte.** The same archive gives the same output files on any machine. _Why:_
anyone should be able to rebuild a published file and get the same bytes; a difference then means
something changed.

**Bitemporal from the start.** The store keeps when each value was published and when we fetched
it, and every revision. _Why:_ revisions are part of the story, and "what was known on that date?"
can't be answered later if it wasn't recorded at the time.

**Standard library first, few dependencies, all pinned.** HTTP, email, HTML and config use the
standard library. The few runtime dependencies are pinned exactly and installed from hashed lock
files; the microdata code's heavier dependencies sit in an optional extra the public pipeline never
installs. _Why:_ every dependency is code we run without having written, and an update we didn't
choose can change results.

**Static files, simple tooling.** Data are published as static files; the site is static pages.
The pipeline is self-hostable and reproducible. _Why:_ static files are cheap to serve, easy to
mirror and archive, and leave nothing to keep running.

**Country codes are ISO 3166-1 alpha-2** in every ID, path and URL; a source's own codes are
translated once, at the boundary. _Why:_ one code per country everywhere, so adding a country never
means renaming.

## Openness

**Open data, no ads.** Everything published is free and stays free: series, methods, code, source
files, revision history. The numbers are never sold: no paid early access, no exclusive data. No
ads. _Why:_ the numbers are only useful if anyone can check and reuse them.

**Open licences.** Code under Apache-2.0, data outputs under CC BY 4.0. Contributions come in under
the same licences, with no contributor agreement.

**Only openly reusable sources.** Paywalled data, and data whose terms forbid redistribution, are
not used. _Why:_ everything we publish must be redistributable, with its sources.

**Privacy by default.** No cookies and nothing loaded from other sites. The published site counts
visits with a cookieless, aggregate-only analytics beacon, disclosed on the About page. The
calculator and the group finder run in the browser; nothing a reader enters is stored or sent.

---

_This page is kept in the repository, in [`wiki/Design-principles.md`](https://github.com/agardelakos/traceconomics/blob/main/wiki/Design-principles.md), and copied here automatically. Changes go through a pull request; an edit made here is replaced at the next update._
