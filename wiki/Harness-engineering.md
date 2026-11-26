# Harness engineering

TracEconomics is built largely with coding agents. This page describes how the repository steers
them, and the people who work alongside them, so that every change keeps the project's promises:
every number traceable, reproducible and honest. The pages in this group go into detail:
[Rules and their guards](Rules-and-their-guards), [Checks](Checks) and
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
brings a harness of its own; its users build an outer one for their own system. That outer harness
has **guides**, which steer the agent before it acts (instructions, conventions), and **sensors**,
which observe the result so the agent can correct itself (tests, linters). Both can be
**computational** (deterministic and fast) or **inferential** (another model judging). Guides alone
never find out whether they worked, and sensors alone let the same mistakes recur.

Here the term means the outer harness: the repository's side. It is not a test harness, a rig for
running code under test.

## The layers in this repository

All of this repository's sensors are computational: they give the same answer every time, and
they run on every change.

| Layer          | What it does                                                                     | Where it lives                                                                                                                                                                                                                                               |
| -------------- | -------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Context        | What an agent or a new contributor reads first: a map, with the reasons          | [`AGENTS.md`](https://github.com/agardelakos/traceconomics/blob/main/AGENTS.md) (vendor-neutral), [CONTRIBUTING.md](https://github.com/agardelakos/traceconomics/blob/main/CONTRIBUTING.md), this wiki, a docstring on every public part, the code reference |
| Guards         | Checks that fail: each hard rule and what enforces it                            | [Rules and their guards](Rules-and-their-guards), [Checks](Checks)                                                                                                                                                                                           |
| Ratchets       | Lists and floors that may only tighten, so a gap can't quietly grow              | [Ratchets and docs as code](Ratchets-and-docs-as-code)                                                                                                                                                                                                       |
| Docs as code   | Tests that fail when a page or a list stops matching the code it describes       | [Ratchets and docs as code](Ratchets-and-docs-as-code)                                                                                                                                                                                                       |
| Feedback loops | Which suite to run for which change, fast local commands, errors that name a fix | `AGENTS.md` ("Definition of done"), [Checks](Checks) ("Run it first")                                                                                                                                                                                        |
| Permissions    | What a change can reach without a person                                         | the branch rules on `main` (required checks), `.github/CODEOWNERS` on the files that steer agents, the agent's own permission settings                                                                                                                       |

The maintainer also keeps private notes (decisions, plans, research) that agents read while
working for them. Nothing in the public repository depends on them.

## Guards are tested too

A guard that has quietly stopped working looks exactly like a clean repository: nothing fails. So
each guard has a **guard test**. It breaks the rule on purpose, in a temporary copy, and expects the
guard to refuse with a message naming the rule. Examples: a fixture with one byte changed; a test
that calls another host and swallows the error; an e-mail address in a source file; a new
`test.skip`; `import pandas` outside the microdata code; an English text without its Greek twin; an
inline script on a built page. [Rules and their guards](Rules-and-their-guards) links each rule to
its guard tests. The idea is the same as mutation testing, applied to the project's rules instead of
its code.

## Error messages that name the fix

A sensor is most useful when its message says what to do. The guards here aim for that:

- the network guard: "tests never call the network (AGENTS.md, hard rules): use a saved fixture or a
  server on 127.0.0.1";
- the skip ratchet: "fix the test, or add the skip to tests/skips.toml with its reason";
- the banned imports: "pandas only in src/traceconomics/local/ ...; a test uses
  pytest.importorskip";
- the site checks: each failure names the page and the rule, and points to a report command where
  one exists (`npm run terms:report`, `npm run figures:report`).

## What stays with people

Some rules are judgements, not patterns: whether a parser has started to guess, or whether a
changed tolerance hides a real difference from an official figure. Machines can't see those, so they
are marked "review only" on [Rules and their guards](Rules-and-their-guards), each with its reason.
The harness doesn't try to remove people from the work. It sends their attention to those rules.

---

_This page is kept in the repository, in [`wiki/Harness-engineering.md`](https://github.com/agardelakos/traceconomics/blob/main/wiki/Harness-engineering.md), and copied here automatically. Changes go through a pull request; an edit made here is replaced at the next update._
