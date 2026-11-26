# Ratchets and docs as code

Two kinds of computational sensor that keep the repository's rules from quietly wearing away. Part
of [Harness engineering](Harness-engineering).

## Ratchets: lists and floors that may only tighten

Some rules have exceptions today that can't be removed at once. A ratchet is a sensor with a stored
baseline: it lists each exception with its reason, and it fails both ways: on a new exception, until
it is added to the list (where a reviewer sees it in the diff), and on an entry that is no longer
needed, until it is removed. So the list stays exact, and it can only shrink unless a person agrees
that it should grow. A floor works the same way upwards: it may rise, never fall. One list only ever
grows, and that is its tightening: the IDs of removed or renamed tests, which can never be used
again.

| Ratchet                 | What it lists                                                                                     | Checked by                                                               |
| ----------------------- | ------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------ |
| Skips                   | every skip, skipif, xfail, `test.skip` and `test.fixme` in the test code, per file, with a reason | `tests/skips.toml`, `tests/test_skips.py`                                |
| Private text            | where an e-mail address or a local path is expected in a source file, with a reason               | `tests/private_text.toml`, `tests/test_private_text.py`                  |
| Glossary terms in Greek | the English and Greek pairs that may still say one concept two ways                               | `site/src/i18n/terms-allow.json`, site check 9                           |
| Figures typed into text | every number with a unit written into the text instead of read from the data                      | `site/src/i18n/figures-allow.json`, site check 11                        |
| Test cases              | the rules every test case must meet; `all = true` makes each rule an error in every file          | `tests/catalog/strict.toml`, the `catalog` job                           |
| Python coverage         | a floor that started at the first measured total and only ever goes up                            | `tests/coverage/overview.py` (`RATCHET`)                                 |
| Removed test IDs        | the IDs of removed or renamed tests, which can never be used again                                | the `catalog` job, from the run history and `tests/catalog/renamed.toml` |

## Docs as code: pages that can't drift

The guides are documents, and a document that describes code is wrong as soon as the code changes,
unless a sensor fails. Each of these tests reads a document and the code it describes, and fails
when they disagree, so the guides and the sensors stay in step:

| Document                                              | What keeps it true                                                                                                                                |
| ----------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| [Checks](Checks)                                      | every CI job, showcase job, scheduled run and release step has exactly one entry in its registry (`tests/test_checks_page.py`)                    |
| [Rules: guides and sensors](Rules-guides-and-sensors) | the registry holds exactly the hard rules in `AGENTS.md`, each with a guide, and every test and file it names exists (`tests/test_rules_page.py`) |
| The wiki's hand-written pages                         | every file and test ID they name exists, every wiki link has a page, every quoted block matches its docstring (`tests/test_wiki_pages.py`)        |
| The code reference                                    | every public module, function and class has a docstring whose first line is a sentence (`tests/test_docstrings.py`)                               |
| The survey tables' fingerprints                       | every file that can change the tables is covered (`tests/test_survey_tables.py`)                                                                  |
| `security.txt`                                        | its contacts match `SECURITY.md` (`tests/test_security_txt.py`)                                                                                   |
| The lock files                                        | they match `pyproject.toml`'s pins (`tests/test_lock_files.py`)                                                                                   |
| The site checks' list of private text                 | the same kinds as the source scan (`tests/test_private_text.py`)                                                                                  |

The generated pages ([Checks](Checks), [Rules: guides and sensors](Rules-guides-and-sensors), the test
pages, the code reference and the code map) go further: they are written from the repository on every wiki run, and the
generator refuses to write while its sources disagree. Nobody edits them by hand.

---

_This page is kept in the repository, in [`wiki/Ratchets-and-docs-as-code.md`](https://github.com/agardelakos/traceconomics/blob/main/wiki/Ratchets-and-docs-as-code.md), and copied here automatically. Changes go through a pull request; an edit made here is replaced at the next update._
