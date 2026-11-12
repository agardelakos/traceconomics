"""The README's two coverage badges, each total split by the layer of test that covers it.

    python tests/coverage/overview.py --python .coverage --site site/coverage/summary.json --out badges/

Back-end: the Python package (src/traceconomics), from coverage.py's data file. tests/conftest.py
labels every line run with the layer of the test running it (a dynamic context: `unit` or
`integration`). Front-end: the site's own code, from the summary `site/scripts/coverage.mjs` writes,
which counts the covered lines of each layer the same way (unit, integration, e2e).

Both count lines: of the lines that hold code, the share run by at least one test. A line run by
tests of several layers counts once, for the lowest of them (unit, then integration, then e2e): the
second part reads "what integration tests add beyond the unit tests", the third "what only the
browser reaches". The total is rounded down to a tenth (never claim more); the parts share it by
largest remainder, so they always add up to the total shown.

Writes <out>/summary.json, <out>/coverage-back-end.svg and <out>/coverage-front-end.svg. Exits
non-zero if a covered line has no layer, or a `repository` test ran package code: either means the
labels are wrong, and a split built on them would be too. With --strict, also if the back-end total
is below RATCHET.
"""

import argparse
import json
import sys
from html import escape
from pathlib import Path

ORDER = ("unit", "integration", "e2e")  # the lowest layer first

# The back-end's standing, the same bounds as the site's (site/scripts/coverage-options.mjs): red
# below FLOOR, yellow from FLOOR, green from GOOD.
FLOOR = 90
GOOD = 95
# The run fails below RATCHET (--strict). FLOOR is the aim, but the measured baseline was 73.9% when
# coverage was first measured (2026-11-07), so failing below 90 would fail every run. RATCHET starts
# at that baseline, rounded down to a whole percent, and only ever goes up: raise it as tests are
# added, never lower it to pass a run. When it reaches FLOOR, it is the floor, as on the site.
# Reached on 2026-11-07, when the measured total rose to 97.4%: the run now fails below 90%.
RATCHET = 90.0
NAMES = {"unit": "unit", "integration": "integration", "e2e": "e2e"}
LONG = {"unit": "unit tests", "integration": "integration tests", "e2e": "end-to-end tests in a browser"}


def split(total: int, covered: dict[str, int]) -> tuple[int, dict[str, int]]:
    """(total in tenths of a percent, each layer's part in tenths) from line counts.

    The total is rounded down; the parts are rounded down, then the tenths still missing go to the
    parts with the largest remainders (ties to the lower layer), so they sum to the total exactly.
    """
    if total <= 0:
        return 0, {k: 0 for k in covered}
    tenths = 1000 * sum(covered.values()) // total
    parts = {k: 1000 * v // total for k, v in covered.items()}
    missing = tenths - sum(parts.values())
    by_remainder = sorted(covered, key=lambda k: (-(1000 * covered[k] % total), ORDER.index(k)))
    for k in by_remainder[:missing]:
        parts[k] += 1
    return tenths, parts


def standing(pct: float) -> str:
    """'low' below FLOOR, 'fair' up to GOOD, 'good' from GOOD: the total's colour on the badge."""
    return "low" if pct < FLOOR else "fair" if pct < GOOD else "good"


def assign(contexts: set[str], layers: tuple[str, ...]) -> str | None:
    """The layer a covered line counts for: the lowest of those that ran it."""
    return next((k for k in layers if k in contexts), None)


def back_end(data_file: Path) -> dict:
    """Lines per layer for the package, from a (combined) coverage.py data file."""
    from coverage import Coverage

    cov = Coverage(data_file=str(data_file))
    cov.load()
    data = cov.get_data()
    layers = ("unit", "integration")
    files, problems = {}, []
    for path in sorted(data.measured_files()):
        statements = set(cov.analysis2(path)[1])
        by_line = data.contexts_by_lineno(path)
        counts = dict.fromkeys(layers, 0)
        for line in sorted(statements & set(by_line)):
            ctx = set(by_line[line])
            layer = assign(ctx, layers)
            if "repository" in ctx:
                problems.append(f"{path}:{line} ran in a repository test (it should run no package code)")
            elif layer is None:
                problems.append(f"{path}:{line} ran with no layer ({', '.join(sorted(ctx)) or 'no context'})")
            if layer is not None:
                counts[layer] += 1
        files[Path(path).as_posix()] = {"total": len(statements), **counts}
    return {"files": files, "problems": problems}


def front_end(summary_file: Path) -> dict:
    """Lines per layer for the site's code, from site/scripts/coverage.mjs's summary."""
    summary = json.loads(summary_file.read_text(encoding="utf-8"))
    return {
        "files": summary["layers"]["files"],
        "problems": summary["layers"].get("problems", []),
        "standing": summary.get("standing"),
    }


def totals(files: dict, layers: tuple[str, ...]) -> dict:
    total = sum(f["total"] for f in files.values())
    covered = {k: sum(f[k] for f in files.values()) for k in layers}
    tenths, parts = split(total, covered)
    return {
        "lines": total,
        "covered": sum(covered.values()),
        "pct": tenths / 10,
        "layers": {k: {"lines": covered[k], "pct": parts[k] / 10} for k in layers},
    }


# The badge. Drawn here rather than by a badge service, so no third party sees or serves it.
# Segment colours: the label grey, the total by its standing, one colour per layer. All take white
# text at 4.5:1 or more.
LABEL = "#555"
TOTAL = {"good": "#2e7d32", "fair": "#8a6d00", "low": "#c62828"}
LAYER = {"unit": "#1c5fb0", "integration": "#6741d9", "e2e": "#a61e4d"}


def width(text: str) -> int:
    """About 6.5 px a character at 11 px Verdana, plus padding (as shields-style badges measure)."""
    return round(len(text) * 6.5) + 12


def badge(name: str, result: dict, level: str) -> str:
    """The badge's SVG; `level` (a standing) colours the total."""
    pct = lambda v: f"{v:.1f}%"
    segments = [(f"{name} coverage", LABEL), (pct(result["pct"]), TOTAL[level])]
    segments += [(f"{NAMES[k]} {pct(v['pct'])}", LAYER[k]) for k, v in result["layers"].items()]
    parts = ", ".join(f"{LONG[k]} {pct(v['pct'])}" for k, v in result["layers"].items())
    title = (
        f"{name.capitalize()} coverage: {pct(result['pct'])} of lines with code are run by a test "
        f"({result['covered']} of {result['lines']}): {parts}. A line run by several kinds of test "
        f"counts once, for the first of unit, integration, end-to-end."
    )
    x, rects, texts = 0, [], []
    for text, colour in segments:
        w = width(text)
        rects.append(f'<rect x="{x}" width="{w}" height="20" fill="{colour}"/>')
        texts.append(f'<text x="{x + w / 2}" y="14">{escape(text)}</text>')
        x += w
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{x}" height="20" role="img" '
        f'aria-label="{escape(title)}">\n<title>{escape(title)}</title>\n'
        f'<clipPath id="r"><rect width="{x}" height="20" rx="3"/></clipPath>\n'
        f'<g clip-path="url(#r)">\n' + "\n".join(rects) + "\n</g>\n"
        f'<g fill="#fff" text-anchor="middle" font-family="Verdana,DejaVu Sans,sans-serif" font-size="11">\n'
        + "\n".join(texts)
        + "\n</g>\n</svg>\n"
    )


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--python", type=Path, required=True, help="coverage.py data file (combined)")
    p.add_argument("--site", type=Path, required=True, help="site/coverage/summary.json")
    p.add_argument("--out", type=Path, required=True, help="folder for summary.json and the badges")
    p.add_argument("--strict", action="store_true", help=f"fail if the back-end total is below {RATCHET}%%")
    a = p.parse_args(argv)

    back, front = back_end(a.python), front_end(a.site)
    summary = {
        "back-end": totals(back["files"], ("unit", "integration")) | {"files": back["files"]},
        "front-end": totals(front["files"], ORDER) | {"files": front["files"]},
    }
    problems = back["problems"] + front["problems"]
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "summary.json").write_text(json.dumps(summary, indent=1) + "\n", encoding="utf-8", newline="\n")
    standings = {"back-end": standing(summary["back-end"]["pct"]), "front-end": front["standing"]}
    for name, level in standings.items():
        (a.out / f"coverage-{name}.svg").write_text(badge(name, summary[name], level), encoding="utf-8", newline="\n")
        s = summary[name]
        print(
            f"{name} coverage {s['pct']}% ({s['covered']} of {s['lines']} lines): "
            + ", ".join(f"{k} {v['pct']}%" for k, v in s["layers"].items())
        )
    failed = False
    if problems:
        print(f"{len(problems)} covered lines with a wrong or missing layer:", *problems[:20], sep="\n  ")
        failed = True
    back_pct = summary["back-end"]["pct"]
    if a.strict and back_pct < RATCHET:
        print(f"back-end coverage {back_pct}% is below the ratchet, {RATCHET}% (tests/coverage/overview.py)")
        failed = True
    elif back_pct < FLOOR:
        print(f"back-end coverage is below the {FLOOR}% aim; the ratchet is at {RATCHET}%")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
