// The series chart: lines for the chosen groups, a shaded span where the data carry a quality
// flag, and, when the poorest and richest fifth are both shown, the gap between them in its own
// panel below (never a second axis), with its error band where the survey design allows one.
//
// Colours are the design tokens (CSS custom properties), so light and dark mode follow the
// reader's setting. Every chart also has a data table and a one-sentence summary on the page,
// so nothing depends on this script running.

import * as Plot from "@observablehq/plot";

export interface Line {
  key: string;
  label: string;           // shown at the line's end
  color: string;           // e.g. "var(--series-q1)"
  dash?: string;           // e.g. "6 4"
  values: (number | null)[];
}

export interface ChartSpec {
  axis: string[];          // "YYYY-MM", one per value
  lines: Line[];
  unit: string;            // "%" or ""
  locale: string;
  flag?: { to: string; fill: string };
  gap?: { values: (number | null)[]; se: (number | null)[]; title: string };
  from?: string;           // first month to show
}

const date = (p: string) => new Date(Date.UTC(Number(p.slice(0, 4)), Number(p.slice(5, 7)) - 1, 1));

function nudge(ys: { y: number; key: string }[], px: number, scale: (v: number) => number) {
  // Spread end labels that would overlap, keeping their order: done in pixels.
  const sorted = ys.map((d) => ({ ...d, py: scale(d.y) })).sort((a, b) => a.py - b.py);
  for (let i = 1; i < sorted.length; i++) {
    if (sorted[i].py - sorted[i - 1].py < px) sorted[i].py = sorted[i - 1].py + px;
  }
  return new Map(sorted.map((d) => [d.key, d.py - scale(d.y)]));
}

/** The chart's panels: the series, then (if asked) the gap. Sized to `width` pixels. */
export function draw(width0: number, spec: ChartSpec): Element[] {
  const from = spec.from ?? spec.axis[0];
  const start = Math.max(0, spec.axis.indexOf(from));
  const axis = spec.axis.slice(start);
  const width = Math.max(300, width0);
  const narrow = width < 600;
  // Phones get a taller chart for their width: the lines need vertical room more than width.
  const height = narrow ? Math.max(260, Math.round(width * 0.8)) : Math.round(Math.min(380, width * 0.42));
  const marginRight = narrow ? 92 : 132;
  const num = new Intl.NumberFormat(spec.locale, { minimumFractionDigits: 1, maximumFractionDigits: 1, signDisplay: "negative" });
  const points = spec.lines.flatMap((l) =>
    l.values.slice(start).map((v, i) => ({ key: l.key, date: date(axis[i]), v: v ?? NaN })));
  const values = points.map((p) => p.v).filter((v) => !Number.isNaN(v));
  const lo = Math.min(0, ...values);
  const hi = Math.max(0, ...values);
  const x = { type: "utc" as const, domain: [date(axis[0]), date(axis[axis.length - 1])], label: null };
  const yScale = (v: number) => 20 + ((hi - v) / (hi - lo || 1)) * (height - 50);
  const ends = spec.lines.map((l) => {
    const vals = l.values.slice(start);
    let i = vals.length - 1;
    while (i > 0 && vals[i] === null) i--;
    return { key: l.key, i, y: vals[i] ?? 0, label: `${l.label} ${num.format(vals[i] ?? 0)}${spec.unit}` };
  });
  const dy = nudge(ends.map((e) => ({ key: e.key, y: e.y })), 13, yScale);
  const marks: Plot.Markish[] = [];
  if (spec.flag && spec.flag.to >= axis[0]) {
    marks.push(Plot.rectX([{ x1: date(axis[0]), x2: date(spec.flag.to < axis[axis.length - 1] ? spec.flag.to : axis[axis.length - 1]) }],
      { x1: "x1", x2: "x2", fill: spec.flag.fill }));
  }
  marks.push(Plot.gridY({ stroke: "var(--chart-grid)", strokeOpacity: 1 }));
  marks.push(Plot.ruleY([0], { stroke: "var(--chart-axis)" }));
  for (const l of spec.lines) {
    marks.push(Plot.lineY(points.filter((p) => p.key === l.key), {
      x: "date", y: "v", stroke: l.color, strokeWidth: 2, strokeDasharray: l.dash, curve: "linear",
    }));
  }
  for (const e of ends) {
    // One mark per label: Plot's dy is a constant, and each label has its own nudge.
    marks.push(Plot.text([e], {
      x: (d) => date(axis[d.i]), y: "y", text: "label", textAnchor: "start", dx: 6, dy: dy.get(e.key) ?? 0,
      fill: "var(--color-text)", fontWeight: 600, fontSize: narrow ? 11 : 13,
    }));
  }
  marks.push(Plot.ruleX(points, Plot.pointerX({ x: "date", stroke: "var(--chart-axis)", strokeOpacity: 0.5 })));
  marks.push(Plot.tip(points.filter((p) => !Number.isNaN(p.v)), Plot.pointerX({
    x: "date", y: "v",
    title: (p) => `${spec.lines.find((l) => l.key === p.key)?.label}: ${num.format(p.v)}${spec.unit}`,
  })));
  const top = Plot.plot({
    width, height, marginLeft: 40, marginRight, marginTop: 16, x,
    y: { label: null, tickFormat: (v: number) => `${v}${spec.unit}`, nice: true },
    style: { background: "transparent", color: "var(--color-text-muted)", fontFamily: "var(--font-sans)", fontSize: "12px" },
    marks,
  });
  const parts: Element[] = [top];
  if (spec.gap) {
    const g = spec.gap.values.slice(start).map((v, i) => {
      const se = spec.gap!.se[start + i];
      return { date: date(axis[i]), v: v ?? NaN, lo: v !== null && se !== null ? v - 2 * se : NaN, hi: v !== null && se !== null ? v + 2 * se : NaN, band: se !== null };
    });
    const noBand = g.filter((d) => !d.band && !Number.isNaN(d.v));
    const gapMarks: Plot.Markish[] = [];
    if (noBand.length) {
      gapMarks.push(Plot.rectX([{ x1: noBand[0].date, x2: noBand[noBand.length - 1].date }],
        { x1: "x1", x2: "x2", fill: "var(--color-disabled)" }));
    }
    gapMarks.push(
      Plot.areaY(g, { x: "date", y1: "lo", y2: "hi", fill: "var(--color-text)", fillOpacity: 0.12 }),
      Plot.ruleY([0], { stroke: "var(--chart-axis)" }),
      Plot.lineY(g, { x: "date", y: "v", stroke: "var(--series-all)", strokeWidth: 2 }),
      Plot.tip(g.filter((d) => !Number.isNaN(d.v)), Plot.pointerX({ x: "date", y: "v", title: (d) => `${spec.gap!.title}: ${num.format(d.v)}` })),
    );
    parts.push(Plot.plot({
      width, height: narrow ? 120 : 140, marginLeft: 40, marginRight, marginTop: 8, x,
      y: { label: null, nice: true, ticks: 3 },
      style: { background: "transparent", color: "var(--color-text-muted)", fontFamily: "var(--font-sans)", fontSize: "12px" },
      marks: gapMarks,
    }));
  }
  // The container carries the chart's description (role="img" and a label) and the page has the
  // data table, so the drawing itself is hidden from screen readers.
  for (const part of parts) part.setAttribute("aria-hidden", "true");
  return parts;
}

/** Draw into `top` (and `gap`, for the gap panel) now, and again whenever the width changes.
 *  Returns a function that redraws with a fresh spec. */
export function mount(top: HTMLElement, gap: HTMLElement | null, spec: () => ChartSpec): () => void {
  let pending = 0;
  let last = -1;
  const el = top;
  const run = () => {
    // A hidden chart (the other view is showing) has no width: draw it when it is shown.
    if (el.clientWidth === 0 || el.clientWidth === last) return;
    last = el.clientWidth;
    const s = spec();
    const [series, gapPanel] = draw(el.clientWidth, s);
    top.replaceChildren(series);
    if (gap) {
      gap.hidden = !gapPanel;
      gap.replaceChildren(...(gapPanel ? [gapPanel] : []));
    }
  };
  run();
  const ro = new ResizeObserver(() => {
    cancelAnimationFrame(pending);
    pending = requestAnimationFrame(run);
  });
  ro.observe(el);
  return () => { last = -1; run(); };
}
