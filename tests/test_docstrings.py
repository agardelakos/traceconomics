"""Every part of the package's public interface says what it is for, in a docstring.

The wiki's code reference is generated from these docstrings, and its summaries show each one's first
line, so that line has to be a whole sentence on its own. Public means: every module, every top-level
function or class whose name has no leading underscore, and every such method of a public class.
Private helpers are optional. There is no allow-list: a new public function without a docstring fails
here. The tests parse the source; nothing is imported or run.
"""

import ast
import re
from collections.abc import Iterator
from pathlib import Path

import pytest

pytestmark = pytest.mark.repository

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "src" / "traceconomics"
LINE_LENGTH = 120  # the project's line length (pyproject.toml, [tool.ruff])

# A sentence ends at a full stop followed by a space and a capital letter; "e.g. the" doesn't end one.
SENTENCE_END = re.compile(r"[.!?] +[A-Z]")

Documented = ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef


def public_parts(tree: ast.Module) -> Iterator[tuple[str, Documented]]:
    """The module, its public top-level functions and classes, and the public methods of those classes."""
    yield "<module>", tree
    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) and not node.name.startswith("_"):
            yield node.name, node
            if isinstance(node, ast.ClassDef):
                for member in node.body:
                    if isinstance(member, ast.FunctionDef | ast.AsyncFunctionDef) and not member.name.startswith("_"):
                        yield f"{node.name}.{member.name}", member


def modules() -> Iterator[tuple[str, ast.Module, list[str]]]:
    for path in sorted(PACKAGE.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        yield path.relative_to(ROOT).as_posix(), ast.parse(source), source.splitlines()


def test_the_package_has_modules_to_check():
    """PY-DOCS-001: The docstring checks find the package's modules

    Given the repository's source folder
    When the docstring checks list the package's modules and their public parts
    Then they find the package's modules, so the other checks can't pass on an empty list
    And they find public functions and classes to check, not only module docstrings
    """
    found = list(modules())
    assert len(found) > 50, f"only {len(found)} modules under {PACKAGE.relative_to(ROOT)}"
    parts = [name for _, tree, _ in found for name, _ in public_parts(tree) if name != "<module>"]
    assert len(parts) > 200, f"only {len(parts)} public functions, classes and methods"


def test_every_public_part_has_a_docstring():
    """PY-DOCS-002: Every module, public function, class and method has a docstring

    Given every module of the package
    When its module docstring, its public top-level functions and classes and their public methods are read
    Then each one has a docstring
    And the failure lists every one that hasn't, with its file and line
    """
    missing = [
        f"{rel}:{getattr(node, 'lineno', 1)}: {name}"
        for rel, tree, _ in modules()
        for name, node in public_parts(tree)
        if ast.get_docstring(node) is None
    ]
    assert not missing, "no docstring:\n" + "\n".join(missing)


def test_every_docstring_starts_with_one_sentence_on_one_line():
    """PY-DOCS-003: Every public docstring starts with one whole sentence on its first line

    Given every public docstring of the package
    When its first line is read
    Then it is not empty and ends with a full stop
    And it holds one sentence only
    And the line, with its indentation and quotes, fits the project's line length
    And the failure lists every docstring that breaks a rule, with the rule
    """
    wrong = []
    for rel, tree, lines in modules():
        for name, node in public_parts(tree):
            docstring = ast.get_docstring(node, clean=False)
            if docstring is None:
                continue  # PY-DOCS-002's failure
            first = docstring.lstrip("\n").splitlines()[0].strip() if docstring.strip() else ""
            where = f"{rel}:{node.body[0].lineno}: {name}"
            if not first:
                wrong.append(f"{where}: empty first line")
            elif not first.endswith("."):
                wrong.append(f"{where}: first line doesn't end a sentence: {first!r}")
            elif SENTENCE_END.search(first):
                wrong.append(f"{where}: more than one sentence on the first line: {first!r}")
            physical = lines[node.body[0].lineno - 1]
            if len(physical) > LINE_LENGTH:
                wrong.append(f"{where}: first line is {len(physical)} characters, over {LINE_LENGTH}")
    assert not wrong, "first lines to fix:\n" + "\n".join(wrong)
