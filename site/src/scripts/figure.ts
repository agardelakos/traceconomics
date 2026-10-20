// A chart figure built at build time with its numbers, summary and table: this script only
// fetches the same series file and draws the chart into it. Without the script the figure still
// says everything in text and in the table.

import { mount, type ChartSpec } from "./chart";

interface FigureSpec {
  src: string;
  locale: string;
  lines: { key: string; label: string; color: string; dash?: string }[];
  gap?: { group: string; title: string };
  flag?: { to: string; fill: string };
  from?: string;
}

function axisOf(start: string, end: string): string[] {
  const out: string[] = [];
  let y = Number(start.slice(0, 4));
  let m = Number(start.slice(5, 7));
  for (;;) {
    const p = `${y}-${String(m).padStart(2, "0")}`;
    if (p > end) return out;
    out.push(p);
    if (++m > 12) { m = 1; y++; }
  }
}

export async function mountFigure(fig: HTMLElement): Promise<void> {
  const spec: FigureSpec = JSON.parse(fig.dataset.chart ?? "{}");
  const top = fig.querySelector<HTMLElement>(".chart-area");
  const gap = fig.querySelector<HTMLElement>(".chart-gap");
  if (!top) return;
  const res = await fetch(spec.src);
  if (!res.ok) return;                      // the table and the summary still carry the numbers
  const data = await res.json();
  const axis = axisOf(data.start, data.end);
  const chart = (): ChartSpec => ({
    axis,
    locale: spec.locale,
    unit: "%",
    from: spec.from,
    flag: spec.flag,
    lines: spec.lines.map((l) => ({ ...l, values: data.groups[l.key].rch_a })),
    gap: spec.gap ? { values: data.gaps[spec.gap.group].rch_a, se: data.gaps[spec.gap.group].se_a, title: spec.gap.title } : undefined,
  });
  mount(top, gap, chart);
}
