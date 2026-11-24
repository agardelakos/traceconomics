"""The code map's charts for the wiki: stacked bars and heatmaps as SVG files, light and dark.

GitHub shows an `.svg` from the wiki's own repository in an `<img>`, but runs no script on a wiki
page, so the charts are static: each one comes with a table of the same numbers under it (the
pages' job, tests/catalog/code_reference.py), and the light and dark versions are chosen by the
reader's colour scheme through `<picture>`.

- Stacked bars: one bar per area or module, its length the lines with code, its segments the lines by
  status (the lowest layer of test that runs them, then imported, then none), so they add up to the bar.
- Heatmap: rows against suites; each cell the share of the row's lines that suite runs at all, so a
  line run by several suites counts in each.

Colours: blue, orange and green for the layers, in the order a palette checked for colour-blind
readers and for both modes was checked in (adjacent segments stay apart); two neutral greys for
"imported" and "none", the lighter one "none". A single blue ramp for the heatmap.

Standard library only. The same rows give the same bytes.
"""

from __future__ import annotations

from html import escape

WIDTH = 880
FONT = "system-ui, -apple-system, Segoe UI, Helvetica, Arial, sans-serif"
THEMES = {
    "light": {
        "surface": "#fcfcfb",
        "ink": "#0b0b0b",
        "ink2": "#52514e",
        "muted": "#898781",
        "grid": "#e1e0d9",
        "axis": "#c3c2b7",
        "status": {
            "unit": "#2a78d6",
            "integration": "#eb6834",
            "e2e": "#1baf7a",
            "imported": "#9e9c94",
            "none": "#e1e0d9",
        },
        "ramp": ["#f0efec", "#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"],
        "dark_text_from": 4,  # ramp steps from here take white text
        "na": "#f0efec",
    },
    "dark": {
        "surface": "#1a1a19",
        "ink": "#f0efec",
        "ink2": "#c3c2b7",
        "muted": "#898781",
        "grid": "#2c2c2a",
        "axis": "#383835",
        "status": {
            "unit": "#3987e5",
            "integration": "#d95926",
            "e2e": "#199e70",
            "imported": "#6b6a65",
            "none": "#383835",
        },
        "ramp": ["#383835", "#104281", "#184f95", "#1c5cab", "#256abf", "#3987e5", "#6da7ec", "#9ec5f4"],
        "dark_text_from": 0,
        "light_text_from": 6,  # the lightest steps take dark text
        "na": "#262624",
    },
}
STATUS_ORDER = ("unit", "integration", "e2e", "imported", "none")


def text_width(s: str, size: float) -> float:
    """About how wide a string is in the chart's font: enough to fit or shorten a label."""
    return len(s) * size * 0.56


def fit(s: str, size: float, room: float) -> str:
    """The label, shortened with an ellipsis when it doesn't fit `room`."""
    if text_width(s, size) <= room:
        return s
    while s and text_width(s + "…", size) > room:
        s = s[:-1]
    return s + "…"


def share(n: int, total: int) -> str:
    """A share as a whole percent, "<1%" for a small one that isn't nothing."""
    if not total:
        return "–"
    return "<1%" if 0 < 100 * n / total < 0.5 else f"{100 * n / total:.0f}%"


def svg(body: list[str], height: int, title: str, theme: dict) -> str:
    """A whole chart: its title for screen readers, its surface, its marks."""
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{height}" '
        f'viewBox="0 0 {WIDTH} {height}" role="img" aria-labelledby="t" font-family="{FONT}">'
        f'<title id="t">{escape(title)}</title>'
        f'<rect width="{WIDTH}" height="{height}" rx="6" fill="{theme["surface"]}"/>' + "".join(body) + "</svg>\n"
    )


def legend(theme: dict, x: float, y: float, statuses: list[str]) -> list[str]:
    """A row of swatches with their names: identity never by colour alone."""
    body = []
    for name in statuses:
        body.append(f'<rect x="{x:.1f}" y="{y - 9}" width="10" height="10" rx="2" fill="{theme["status"][name]}"/>')
        body.append(f'<text x="{x + 15:.1f}" y="{y}" font-size="12" fill="{theme["ink2"]}">{name}</text>')
        x += 15 + text_width(name, 12) + 18
    return body


def nice_max(v: int) -> tuple[int, int]:
    """The axis's end and step: a round number at or above `v`, in at most six steps."""
    for step in (10, 20, 25, 50, 100, 200, 250, 500, 1000, 2000, 2500, 5000):
        if v / step <= 6:
            return max(step, step * -(-v // step)), step
    return v, v


def bars(rows: list[tuple[str, dict]], title: str, theme: dict, label_width: int = 200) -> str:
    """Horizontal stacked bars on one axis; a row ("#", text) is a group heading."""
    pad_l, pad_r, top, row_h, bar_h = 16, 56, 54, 26, 16
    x0, x1 = pad_l + label_width, WIDTH - pad_r
    totals = [sum(c.values()) for lab, c in rows if lab != "#"]
    vmax, step = nice_max(max(totals, default=0) or 1)
    scale = (x1 - x0) / vmax
    h = top + sum(row_h + (10 if lab == "#" else 0) for lab, _ in rows) + 28
    used = [k for k in STATUS_ORDER if any(lab != "#" and c.get(k) for lab, c in rows)]
    body = [f'<text x="{pad_l}" y="24" font-size="14" font-weight="600" fill="{theme["ink"]}">{escape(title)}</text>']
    body += legend(theme, pad_l, 44, used)
    axis_y = h - 24
    for v in range(0, vmax + 1, step):
        gx = x0 + v * scale
        body.append(
            f'<line x1="{gx:.1f}" y1="{top}" x2="{gx:.1f}" y2="{axis_y}" stroke="{theme["grid"]}" stroke-width="1"/>'
        )
        body.append(
            f'<text x="{gx:.1f}" y="{axis_y + 16}" font-size="11" fill="{theme["muted"]}" text-anchor="middle" '
            f'style="font-variant-numeric: tabular-nums">{v:,}</text>'
        )
    body.append(f'<line x1="{x0}" y1="{top}" x2="{x0}" y2="{axis_y}" stroke="{theme["axis"]}" stroke-width="1"/>')
    y = top
    for lab, c in rows:
        if lab == "#":
            y += 10
            body.append(
                f'<text x="{pad_l}" y="{y + 16}" font-size="12" font-weight="600" fill="{theme["muted"]}">'
                f"{escape(c)}</text>"
            )
            y += row_h
            continue
        total = sum(c.values())
        cy = y + (row_h - bar_h) / 2
        body.append(
            f"<g><title>{escape(lab)}: {total:,} lines; "
            + escape(", ".join(f"{k} {c[k]:,}" for k in STATUS_ORDER if c.get(k)))
            + "</title>"
        )
        body.append(
            f'<text x="{x0 - 8}" y="{cy + 12}" font-size="12" fill="{theme["ink2"]}" text-anchor="end">'
            f"{escape(fit(lab, 12, label_width - 8))}</text>"
        )
        segments = [(k, c[k] * scale) for k in STATUS_ORDER if c.get(k)]
        bx = x0
        for i, (k, w) in enumerate(segments):
            last = i == len(segments) - 1
            ww = max(w - (0 if last else 2), 0.8)  # a 2px surface gap between segments
            fill = theme["status"][k]
            if last and ww > 4:  # a 4px rounded end, square at the baseline
                r = 4
                body.append(
                    f'<path d="M{bx:.1f},{cy:.1f} h{ww - r:.1f} a{r},{r} 0 0 1 {r},{r} v{bar_h - 2 * r} '
                    f'a{r},{r} 0 0 1 -{r},{r} h-{ww - r:.1f} z" fill="{fill}"/>'
                )
            else:
                body.append(f'<rect x="{bx:.1f}" y="{cy:.1f}" width="{ww:.1f}" height="{bar_h}" fill="{fill}"/>')
            bx += w
        body.append(
            f'<text x="{x0 + total * scale + 6:.1f}" y="{cy + 12}" font-size="11" fill="{theme["ink2"]}" '
            f'style="font-variant-numeric: tabular-nums">{total:,}</text></g>'
        )
        y += row_h
    return svg(body, h, title, theme)


def heatmap(rows: list[tuple[str, dict]], cols: list[str], title: str, theme: dict, label_width: int = 200) -> str:
    """Rows against columns, each cell a share from 0 to 1, or None for "not measured"."""
    pad_l, top, ch = 16, 76, 26
    cw = min(150, (WIDTH - pad_l - label_width - 16) / len(cols))
    h = top + len(rows) * ch + 14
    body = [f'<text x="{pad_l}" y="24" font-size="14" font-weight="600" fill="{theme["ink"]}">{escape(title)}</text>']
    kx = pad_l
    body.append(f'<text x="{kx}" y="46" font-size="11" fill="{theme["muted"]}">share of lines run:</text>')
    kx += 112
    for i, colour in enumerate(theme["ramp"]):
        body.append(f'<rect x="{kx + i * 26}" y="36" width="24" height="12" rx="2" fill="{colour}"/>')
    body.append(f'<text x="{kx}" y="62" font-size="10" fill="{theme["muted"]}">0%</text>')
    body.append(
        f'<text x="{kx + 8 * 26 - 2}" y="62" font-size="10" fill="{theme["muted"]}" text-anchor="end">100%</text>'
    )
    if any(v is None for _, r in rows for v in r.values()):
        body.append(f'<rect x="{kx + 8 * 26 + 20}" y="36" width="24" height="12" rx="2" fill="{theme["na"]}"/>')
        body.append(f'<text x="{kx + 8 * 26 + 50}" y="46" font-size="11" fill="{theme["muted"]}">not measured</text>')
    x0 = pad_l + label_width
    for j, col in enumerate(cols):
        body.append(
            f'<text x="{x0 + j * cw + cw / 2:.1f}" y="{top - 6}" font-size="12" fill="{theme["ink2"]}" '
            f'text-anchor="middle">{escape(col)}</text>'
        )
    for i, (lab, shares) in enumerate(rows):
        y = top + i * ch
        body.append(
            f'<text x="{x0 - 8}" y="{y + 17}" font-size="12" fill="{theme["ink2"]}" text-anchor="end">'
            f"{escape(fit(lab, 12, label_width - 8))}</text>"
        )
        for j, col in enumerate(cols):
            s = shares.get(col)
            x = x0 + j * cw
            if s is None:
                fill, text, colour = theme["na"], "–", theme["muted"]
            else:
                step = 0 if s == 0 else min(7, 1 + int(s * 7 - 1e-9))
                fill = theme["ramp"][step]
                text = "0" if s == 0 else ("<1%" if s < 0.005 else f"{100 * s:.0f}%")
                white = step >= theme["dark_text_from"] and step < theme.get("light_text_from", 99)
                colour = theme["muted"] if s == 0 else ("#ffffff" if white else "#0b0b0b")
            body.append(
                f"<g><title>{escape(lab)}, {escape(col)}: {escape(text)}</title>"
                f'<rect x="{x + 1:.1f}" y="{y + 1}" width="{cw - 2:.1f}" height="{ch - 2}" rx="3" fill="{fill}"/>'
                f'<text x="{x + cw / 2:.1f}" y="{y + 17}" font-size="11" fill="{colour}" text-anchor="middle" '
                f'style="font-variant-numeric: tabular-nums">{escape(text)}</text></g>'
            )
    return svg(body, h, title, theme)


def pair(stem: str, draw) -> dict[str, str]:
    """The light and dark files of one chart: {file name: SVG}; `draw(theme)` draws it."""
    return {f"{stem}-{mode}.svg": draw(theme) for mode, theme in THEMES.items()}


def picture(stem: str, alt: str) -> str:
    """The chart on a page: the dark file for a dark colour scheme, else the light one."""
    return (
        f'<picture><source media="(prefers-color-scheme: dark)" srcset="{stem}-dark.svg">'
        f'<img src="{stem}-light.svg" alt="{escape(alt)}" width="{WIDTH}"></picture>'
    )


def line(points: list[tuple[str, float]], title: str, theme: dict, unit: str = "%") -> str:
    """A value over time: one point per run, in order, the newest marked larger; the axis from a round
    number below the lowest value to 100."""
    pad_l, pad_r, top, h = 56, 24, 40, 150
    low = min((v for _, v in points), default=100)
    floor = max(0, min(90, int(low // 10) * 10 - (10 if low % 10 < 2 else 0)))
    x0, x1, y0, y1 = pad_l, WIDTH - pad_r, h - 30, top

    def y(v: float) -> float:
        return y0 - (v - floor) / (100 - floor) * (y0 - y1)

    # The points sit inside the axis, so the first clears the value labels and the last date fits.
    inner0, inner1 = x0 + 36, x1 - 40
    step = (inner1 - inner0) / max(1, len(points) - 1)
    xs = [inner0 + i * step if len(points) > 1 else (inner0 + inner1) / 2 for i in range(len(points))]
    body = [f'<text x="16" y="24" font-size="14" font-weight="600" fill="{theme["ink"]}">{escape(title)}</text>']
    for v in (floor, (floor + 100) / 2, 100):
        body.append(
            f'<line x1="{x0}" y1="{y(v):.1f}" x2="{x1}" y2="{y(v):.1f}" stroke="{theme["grid"]}" stroke-width="1"/>'
        )
        body.append(
            f'<text x="{x0 - 8}" y="{y(v) + 4:.1f}" font-size="11" fill="{theme["muted"]}" text-anchor="end" '
            f'style="font-variant-numeric: tabular-nums">{v:g}{unit}</text>'
        )
    colour = theme["status"]["unit"]
    if len(points) > 1:
        path = " ".join(f"{x:.1f},{y(v):.1f}" for x, (_, v) in zip(xs, points, strict=True))
        body.append(f'<polyline fill="none" stroke="{colour}" stroke-width="2" points="{path}"/>')
    for i, (x, (label, v)) in enumerate(zip(xs, points, strict=True)):
        newest = i == len(points) - 1
        body.append(
            f'<g><title>{escape(label)}: {v:g}{unit}</title><circle cx="{x:.1f}" cy="{y(v):.1f}" '
            f'r="{5 if newest else 3.5}" fill="{colour}"/></g>'
        )
        body.append(
            f'<text x="{x:.1f}" y="{h - 10}" font-size="11" fill="{theme["muted"]}" text-anchor="middle">'
            f"{escape(label)}</text>"
        )
    return svg(body, h, title, theme)
