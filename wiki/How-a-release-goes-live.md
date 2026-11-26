# How a release goes live

When ELSTAT or Eurostat publishes new price data, the site should show it the same day, with
nobody needing to be at a keyboard, and never with a wrong number. This page explains how a
release build decides by itself whether it may go live, and how we tested that decision.

**Status:** every build makes the decision today. Since November 2026 it runs in **shadow mode**:
each build reports what it would have done and why, a maintainer still promotes it, and the two
are compared over several release days before the switch is turned on.

## From a publisher's release to a build

1. **Release days come from the publishers' own calendars**, read on every run (ELSTAT's web
   calendar and its yearly PDF for next year's dates; Eurostat's release calendar).
2. **On a release day, a poll checks for the new files** every 5 minutes from 12:00 Greek time,
   the publishers' release time: one request per check, at most 12 per topic before the daily run
   at 13:00. The signal is a new document on the publisher's page (ELSTAT) or a moved "last data
   update" time (Eurostat), not just a changed page. The daily run stays as the fallback, and
   alerts if a release day passes with nothing new.
3. **The new files are archived as received**, and a release build starts. A build that finds
   another one running is queued, not dropped.

## What a build checks

Each step must pass, or the build stops and nothing is published. The steps are listed in
`src/traceconomics/release.py`:

- **Our own inputs are current.** The tables we build from survey microdata must match the code and
  every file they were built from; stale tables stop the build at its first step.
- **The series are rebuilt** for every option combination, then **checked against official
  figures**: the Greek HICP rebuilt from Eurostat's sub-indices and weights (V1), the Greek CPI
  rebuilt from ELSTAT's item indices and weights (V1-CPI), the identities between combinations, and
  our own weights switch for a new year.
- **The site is built and tested**: site checks (translations, links, every figure typed into the
  text), the full browser suite on the built pages, then the files are uploaded as a private
  preview and the smoke tests run again there, against what the host really serves.

## The decision: promote, or hold and say why

A build that passed every step goes to production by itself only when **nothing but the
publishers' data changed** since the build production serves, and the numbers moved as they
normally do. The rules are in `src/traceconomics/release_decision.py`, each with its basis in the
docstring:

| Rule                        | Why                                                                                                                                  |
| --------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| The same code               | A code change always waits for a maintainer, so the first build after a deploy holds.                                                |
| The same own inputs         | A rebuilt survey table changes numbers without any publisher releasing anything.                                                     |
| Something new               | No new publisher file means nothing to publish.                                                                                      |
| No revised value            | Archived copies one release apart revised none of about 555,000 values, so any revision is unusual enough to look at.                |
| No month beyond its record  | Each group's gap to all households, and its monthly change, must stay within the largest in the group's published history (2009 on). |
| The text's figures stand    | A sentence quoting a figure the data can't recompute names its source datasets; if one changed, a person reads the sentence again.   |
| Production is what we think | The live site must serve the build on record, or the comparison would be with the wrong build.                                       |

The rules lean towards holding: a hold costs one promote by hand, while a wrong "fine" puts a wrong
number live. A held build's email names every reason, as loudly as an alert. After an automatic
promote, the email names the build it replaced and the one command that goes back to it. That
build is always kept.

## How we know the checks catch a bad release

**Made-up data in every state real data pass through.** The first two release-day builds both
failed their browser tests, because the real data had moved into a state the made-up test data
never reached: the HICP a month behind the CPI, then catching up. Once it exposed a real bug, once
a test's wrong assumption. CI now builds and tests the site on made-up
data in each such state (`tests/sitedata.py --state`: the HICP behind or caught up, January with a
new year's weights, a new survey year), so that kind of failure shows up in a pull request instead.

**January, replayed on the archive.** January is the riskiest month: both publishers switch to a
new basket of weights, and the index is linked to the previous December. We replayed twelve past
Januaries (2015 to 2026) from the archived files, cut back to what was published on each release
day, and planted the two breaks that matter: the link at the wrong month, and last year's weights
kept.

- The wrong link failed the checks in every January.
- Last year's weights kept passed in half of them. A tolerance can't fix this: a correct January
  misses the official figure by up to 1.1e-4, a broken one by as little as 1.0e-4.
- So the checks now also fail on a structure no tolerance needs: a year whose weights equal the
  year before's (both publishers reweight every year), and a check that stops before the newest
  month we hold. Rerun with those, every broken January failed and every correct one passed (one
  V1 replay aside, an artefact of the replay: its finest level starts in January 2015, so that cut
  has no annual rate yet).

**The new checks are mutation-tested.** Before a check counts, the code it checks is broken on
purpose and the check must fail; where a break survived, the test was strengthened.

**Figures typed into the text.** A number written into a sentence doesn't follow the data. Every
such figure is listed (`site/src/i18n/figures-allow.json`), those the data can recompute are
recomputed in every build, and CI builds the site on two different made-up data sets: a figure
that comes out the same in both was typed in, not read from the data.

## What it doesn't do

- **Code never goes live by itself.** It reaches the build machine only through a deploy, and the
  first build after one always holds.
- **It never fits a number to an official one.** Differences from official figures are published
  and explained; the checks stop arithmetic and reading errors, not disagreement.
- **It doesn't publish part of a release early.** The whole build passes, or nothing goes out.

Test layers and what each proves: [Test strategy](Test-strategy).

---

_This page is kept in the repository, in [`wiki/How-a-release-goes-live.md`](https://github.com/agardelakos/traceconomics/blob/main/wiki/How-a-release-goes-live.md), and copied here automatically. Changes go through a pull request; an edit made here is replaced at the next update._
