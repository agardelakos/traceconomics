# TracEconomics wiki

TracEconomics is an open, transparent tracker of the economy, built only on public data. It
publishes numbers that don't otherwise exist, traces each one to the publishers' original files,
and explains it in plain language. Greece comes first; the design allows many countries.

## Who it is for

- **Anyone curious about the economy.** No expertise needed: every term, series, option and chart
  has a plain explanation.
- **Specialists who need numbers they can cite**: data journalists, policy analysts, unions and
  consumer groups, teachers and students, and people who want to build the same for another
  country. Downloads, method pages and the option switches are there for them.

## What is live

The site, [traceconomics.com](https://traceconomics.com), in English and Greek; the Greek was
reviewed by a native speaker before it was offered.

- **Inflation by household for Greece**: did prices rise the same for everyone? Monthly from 2010,
  by income fifth, renters and owners, and pensioner households, under every combination of the
  method options, with error bands.
- **A personal inflation calculator** and a **group finder**, running entirely in the browser:
  nothing is stored or sent.
- **Rebuilt official figures**: the engine rebuilds Greece's official consumer price indices from
  their published parts, and each country page shows the published figure next to ours.
- **Downloads** in Parquet and CSV, and a glossary.

Behind the site, an archive job keeps every published version of the source files, because
statistical offices revise numbers and overwrite files in place.

More topics and countries are planned.

## How to use this wiki

The repository holds the code and the binding rules; the wiki holds the longer explanations.

| Page                                                     | Read it to                                                   |
| -------------------------------------------------------- | ------------------------------------------------------------ |
| [Architecture](Architecture)                             | understand how data flows from publishers' files to the site |
| [Design principles](Design-principles)                   | know the rules the project keeps, and why                    |
| [Adding a source or country](Adding-a-source-or-country) | plan a new data source or country                            |
| [Test strategy](Test-strategy)                           | see what each test layer proves, and what isn't tested       |
| [Test management as code](Test-management-as-code)       | see how test cases and run history are kept with the code    |
| [Future](Future)                                         | see what is deliberately left for later                      |

Wiki pages follow the current rules on `main`. If a page and the code disagree, the code and
[CONTRIBUTING.md](https://github.com/agardelakos/traceconomics/blob/main/CONTRIBUTING.md) win;
please open an issue.

## Contributing

Start with [CONTRIBUTING.md](https://github.com/agardelakos/traceconomics/blob/main/CONTRIBUTING.md)
in the repository: what is welcome, the process, the hard rules and how to run the tests. Coding
agents have their own instructions in
[AGENTS.md](https://github.com/agardelakos/traceconomics/blob/main/AGENTS.md). Security problems go
through private vulnerability reporting
([SECURITY.md](https://github.com/agardelakos/traceconomics/blob/main/SECURITY.md)).

---

_This page is kept in the repository, in [`wiki/Home.md`](https://github.com/agardelakos/traceconomics/blob/main/wiki/Home.md), and copied here automatically. Changes go through a pull request; an edit made here is replaced at the next update._
