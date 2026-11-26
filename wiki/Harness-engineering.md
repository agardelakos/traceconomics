# Harness engineering

TracEconomics is built largely with coding agents. This page describes how the repository steers
them, and the people who work alongside them, so that every change keeps the project's promises:
every number traceable, reproducible and honest. The other pages in this group go into detail:
[Rules: guides and sensors](Rules-guides-and-sensors), [Checks](Checks) and
[Ratchets and docs as code](Ratchets-and-docs-as-code).

## The term

"Harness engineering" spread in 2026 after an OpenAI engineering post on building a product with
coding agents and no hand-written code ([Harness engineering: leveraging Codex in an agent-first
world](https://openai.com/index/harness-engineering/), 2026-02-11). Its lessons include "give Codex
a map, not a 1,000-page instruction manual", docs checked by machines so they don't drift, and
custom lints whose error messages tell the agent how to fix the problem.

Birgitta Böckeler gave the idea a model on martinfowler.com
([Harness engineering for coding agent users](https://martinfowler.com/articles/harness-engineering.html),
2026-04-02). An agent is the model plus its harness: everything around the model. The coding agent
brings a harness of its own; its users build an outer one for their own system. Here the term means
that outer harness: the repository's side. It is not a test harness, a rig for running code under
test.

Her model has four parts, and this wiki uses its words throughout:

- **Guides** (feedforward) steer the agent before it acts, so the first attempt is more likely
  right. **Sensors** (feedback) observe after it acts, so it can correct itself. Either alone
  fails: without sensors an agent "encodes rules but never finds out whether they worked"; without
  guides it "keeps repeating the same mistakes".
- Both are **computational** (deterministic and fast: tests, linters, structural checks) or
  **inferential** (another model judging: slower, and not the same answer every time).
- **Timing:** "keep quality left". Cheap sensors run before a commit and on every change, expensive
  ones after integration, and some run continuously, against drift that builds up while nobody
  touches the code.
- **Regulation categories:** what a harness keeps in its desired state: maintainability,
  architecture fitness, behaviour.

## Guides and sensors here

|         | Computational                                                                                                                                                                                                                                                                                                                                          | Inferential                                                                                                                                                                                                                                                                                                                                 |
| ------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Guides  | the formatters, run before a commit to rewrite the code; saved publisher files (`tests/fixtures/`) and made-up data (`tests/sitedata.py`), so a test never needs the network or the microdata; the site's components and tokens ([Site patterns](Site-patterns)); `checks.require()`, which makes refusing a surprising file the short path            | instructions a model or a person reads and applies: [`AGENTS.md`](https://github.com/agardelakos/traceconomics/blob/main/AGENTS.md) (vendor-neutral), [CONTRIBUTING.md](https://github.com/agardelakos/traceconomics/blob/main/CONTRIBUTING.md), this wiki, a docstring on every public part and the [code reference](Code) built from them |
| Sensors | the test suites; the linters; the site checks; a sensor for each hard rule a machine can see ([Rules: guides and sensors](Rules-guides-and-sensors)); the ratchets and the docs-as-code tests ([Ratchets and docs as code](Ratchets-and-docs-as-code)); the release checks against official figures; mutation testing. [Checks](Checks) lists them all | none. No model reviews a change here. Where no machine can see a break, a person decides: the rules marked "review only" on [Rules: guides and sensors](Rules-guides-and-sensors)                                                                                                                                                           |

Two more things shape what a change can do, and they are neither guides nor sensors in her model:
the **permissions**. The branch rules on `main` let a change in only through a pull request whose
required checks pass; `.github/CODEOWNERS` asks the maintainer to review the files that steer
agents; and the agent's own permission settings, set by the person running it, decide what it may
do on their machine. The maintainer also keeps private notes (decisions, plans, research) that agents
read while working for them; nothing in the public repository depends on them.

A **gate**, on these pages, is a place where a failed sensor blocks something: a merge, a release
build, a promotion. The word is ours, not the model's.

## When they run

[Checks](Checks) lists every sensor by when it runs, cheapest and earliest first:

- **before a commit:** every check with a command under "Run it first", and `AGENTS.md`'s
  definition of done, which says which to run for which change;
- **on every change:** the pipeline on every pull request; the required checks are the gate to
  `main`;
- **after integration:** the [testing showcase](Testing-showcase) on `main`: a second browser suite,
  the code map, mutation testing (her own example of a sensor for this stage);
- **continuous:** weekly runs, the watchdog on the release server, dependency updates, the
  publishers' reuse terms;
- **runtime:** the release build's checks, which gate the upload and the promotion, and the check
  that the live site serves the promoted build.

## What they regulate

- **Maintainability:** one code style (the linters), a docstring on every public part, the ratchets
  that keep exceptions from growing.
- **Architecture fitness:** pandas and numpy only in the microdata code, outputs reproducible to
  the byte, page budgets, the Content Security Policy, no network in a test.
- **Behaviour:** the test suites, the rebuilt official figures and the other checks against them,
  mutation testing of the engine, the rules that decide whether a release goes live by itself.

Some of the hard rules fit none of the three: that publishers' files are never edited, that
survey microdata never reach the repository, that nothing private is written in it. They keep the
evidence and the households' privacy, not the code. We name them as outside her categories rather
than invent a fourth.

## Sensors are tested too

"If sensors never fire, is that a sign of high quality or inadequate detection mechanisms?" asks
Böckeler. A sensor that has quietly stopped working looks exactly like a clean repository. So each
rule's sensor has a **sensor test**: it breaks the rule on purpose, in a temporary copy, and
expects the sensor to refuse with a message naming the rule. Examples: a fixture with one byte
changed; a test that calls another host and swallows the error; an e-mail address in a source
file; a new `test.skip`; `import pandas` outside the microdata code; an English text without its
Greek twin; an inline script on a built page. [Rules: guides and sensors](Rules-guides-and-sensors)
links each rule to its sensor tests. The idea is the same as mutation testing, applied to the
project's rules instead of its code.

## Error messages that name the fix

A sensor helps most when its message says what to do: "signals that are optimised for LLM consumption",
in Böckeler's words, "a positive kind of prompt injection". The rule sensors aim for that:

- the network sensor: "tests never call the network (AGENTS.md, hard rules): use a saved fixture or
  a server on 127.0.0.1";
- the skip ratchet: "fix the test, or add the skip to tests/skips.toml with its reason";
- the banned imports: "pandas only in src/traceconomics/local/ (AGENTS.md, hard rules); a test uses
  pytest.importorskip";
- the site checks: each failure names the page and the rule, and points to a report command where
  one exists (`npm run terms:report`, `npm run figures:report`).

## The steering loop

"Whenever an issue happens multiple times, the feedforward and feedback controls should be
improved." Two examples from this repository:

- Six of the twelve hard rules once held only while every reader obeyed them. Four got sensors of
  their own (no network in a test, nothing private in the source, the skip ratchet, the banned
  imports), each with its sensor test.
- The first [agent evals](Agent-evals) found a bug in a sensor test itself: its copy of the site
  skipped a folder that was a link. The copy was fixed, so the test now sees what the real build
  sees.

## Three open questions, and the answers here

Böckeler ends with open questions. Three have a working answer in this repository:

- **"How do we keep a harness coherent as it grows, with guides and sensors in sync?"** Docs as
  code: the rules page fails to build when `AGENTS.md` gains or rewords a rule without its guides,
  sensors and sensor tests, and the Checks page when a job or a release step has no entry
  ([Ratchets and docs as code](Ratchets-and-docs-as-code)).
- **"If sensors never fire, is that a sign of high quality or inadequate detection mechanisms?"**
  The sensor tests, above.
- **"We need a way to evaluate harness coverage and quality."** Two ways: each rule's strength and
  its named gap on [Rules: guides and sensors](Rules-guides-and-sensors), and the
  [agent evals](Agent-evals), which give an agent a task whose quickest fix breaks a rule and record
  what it does.

## What stays with people

Some rules are judgements, not patterns: whether a parser has started to guess, or whether a
changed tolerance hides a real difference from an official figure. Machines can't see those, so they
are marked "review only" on [Rules: guides and sensors](Rules-guides-and-sensors), each with its
reason. "A good harness should not necessarily aim to fully eliminate human input, but to direct it
to where our input is most important": the harness sends people's attention to those rules.
