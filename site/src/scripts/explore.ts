// The explore page: groups, options and measure in the address; one setting's file at a time;
// the chart, summary, table, notes, contributions, the link to its files and the citation follow
// the choice.

import { mount, type ChartSpec } from "./chart";
import { fill, month, num, type Lang } from "../lib/format";

interface Config {
  lang: Lang;
  locale: string;
  base: string;
  defaultSlug: string;
  optionKeys: string[];
  values: Record<string, string[]>;
  defaults: Record<string, string>;
  colors: Record<string, string>;
  dash: Record<string, string>;
  availability: Record<string, Record<string, { index: string[]; annual_rates: string[] | null; greyed: any[]; notes: any[] }>>;
  dataPage: string;
  country: string;
  divisions: Record<string, string>;
  strings: Record<string, string>;
}

type Measure = "rch_a" | "rch_m" | "index";
const SETTING_KEYS = ["spending", "imputed_rent", "price_source", "weights_timing", "tutoring"];
const MAX_GROUPS = 6;
const DEFAULT_GROUPS = ["Q1", "Q5", "all/all"];

export function start(root: HTMLElement): void {
  const cfg: Config = JSON.parse(root.dataset.config ?? "{}");
  const L = cfg.lang;
  const t = (key: string, vars: Record<string, string | number> = {}) => {
    const text = cfg.strings[key];
    if (text === undefined) throw new Error(`missing text "${key}"`);
    return fill(text, vars);
  };
  const $ = <T extends HTMLElement>(role: string) => root.querySelector<T>(`[data-role="${role}"]`)!;

  // State, read from the address (unknown values fall back to the defaults).
  const params = new URLSearchParams(location.search);
  const options: Record<string, string> = { ...cfg.defaults };
  for (const k of cfg.optionKeys) {
    const v = params.get(k);
    if (v && cfg.values[k].includes(v)) options[k] = v;
  }
  const allGroups = Array.from(root.querySelectorAll<HTMLButtonElement>("[data-group]")).map((b) => b.dataset.group!);
  let groups = (params.get("groups") ?? "").split(",").filter((g) => allGroups.includes(g)).slice(0, MAX_GROUPS);
  if (!groups.length) groups = [...DEFAULT_GROUPS];
  let measure: Measure = (["rch_a", "rch_m", "index"].includes(params.get("m") ?? "") ? params.get("m") : "rch_a") as Measure;
  // The gap panel (poorest minus richest fifth) is the reader's choice, on by default, whatever
  // groups the main chart shows. It exists for the annual rate only.
  let showGap = params.get("gap") !== "0";
  // Two views of the same selection, in the same card: the series over time, and what made up the
  // latest annual rate. One set of controls drives both.
  type View = "time" | "parts";
  let view: View = params.get("view") === "parts" ? "parts" : "time";
  let tableOpen = false;

  const slug = () => SETTING_KEYS.map((k) => options[k]).join("_");
  const dataKey = (g: string) => (g.startsWith("Q") ? `${options.grouping}/${g}` : g);
  const groupName = (g: string) => t(`group.${g}`);
  const shortName = (g: string) => t(`group.short.${g}`);
  const inSentence = (g: string) => t(`group.in.${g}`);

  // Files, fetched once each.
  const cache = new Map<string, Promise<any>>();
  const load = (rel: string) => {
    if (!cache.has(rel)) {
      cache.set(rel, fetch(`${cfg.base}/${rel}`).then((r) => {
        if (!r.ok) throw new Error(`${r.status} ${rel}`);
        return r.json();
      }).catch((e) => { cache.delete(rel); throw e; }));
    }
    return cache.get(rel)!;
  };

  // Controls.
  for (const input of root.querySelectorAll<HTMLInputElement>("fieldset[data-option] input[type=radio]")) {
    input.checked = options[input.name] === input.value;
    input.addEventListener("change", () => { if (input.checked) { options[input.name] = input.value; render(); } });
  }
  for (const b of root.querySelectorAll<HTMLButtonElement>("[data-group]")) {
    b.addEventListener("click", () => {
      const g = b.dataset.group!;
      if (groups.includes(g)) { if (groups.length > 1) groups = groups.filter((x) => x !== g); }
      else if (groups.length < MAX_GROUPS) groups = [...groups, g];
      render();
    });
  }
  const measureSel = $<HTMLSelectElement>("measure");
  measureSel.value = measure;
  measureSel.addEventListener("change", () => { measure = measureSel.value as Measure; render(); });
  const gapToggle = $<HTMLInputElement>("gap-toggle");
  gapToggle.addEventListener("change", () => { showGap = gapToggle.checked; render(); });
  const viewButtons = Array.from(root.querySelectorAll<HTMLButtonElement>("[data-view]"));
  for (const b of viewButtons) b.addEventListener("click", () => { view = b.dataset.view as View; render(); });
  // The data points are a fold; the table is built only while it is open.
  const tableFold = $<HTMLDetailsElement>("table-fold");
  tableFold.addEventListener("toggle", () => { tableOpen = tableFold.open; render(); });

  // Full screen: the chart alone (title, summary, chart, gap panel, legend, notes), for a reader
  // who has set the groups and options and now wants to look at it. The chart redraws for the new
  // width by itself. Shown only where the browser allows it (not on iPhones, for instance).
  const block = $("chart-figure");
  const fullscreen = $<HTMLButtonElement>("fullscreen");
  if (document.fullscreenEnabled && block.requestFullscreen) {
    fullscreen.hidden = false;
    fullscreen.addEventListener("click", () => {
      if (document.fullscreenElement) document.exitFullscreen();
      else block.requestFullscreen().catch(() => { /* refused: the page stays as it is */ });
    });
    document.addEventListener("fullscreenchange", () => {
      const on = Boolean(document.fullscreenElement);
      const label = t(on ? "chart.fullscreen_exit" : "chart.fullscreen");
      fullscreen.classList.toggle("is-on", on);
      fullscreen.setAttribute("aria-label", label);
      fullscreen.title = label;
    });
  }
  $<HTMLButtonElement>("retry").addEventListener("click", () => render());

  let redraw: (() => void) | null = null;
  let current: ChartSpec | null = null;
  let seq = 0;

  function syncControls() {
    for (const b of root.querySelectorAll<HTMLButtonElement>("[data-group]")) {
      const on = groups.includes(b.dataset.group!);
      b.setAttribute("aria-pressed", String(on));
      b.disabled = !on && groups.length >= MAX_GROUPS;
    }
    $("group-count").textContent = t("explore.groups_max", { n: groups.length, max: MAX_GROUPS });
    const changed = cfg.optionKeys.filter((k) => options[k] !== cfg.defaults[k]).length;
    $("changed").textContent = changed ? t("option.changed", { n: changed }) : t("option.all_defaults");
    for (const fs of root.querySelectorAll<HTMLElement>("fieldset[data-option]")) {
      const k = fs.dataset.option!;
      const note = fs.querySelector<HTMLElement>('[data-role="note"]')!;
      note.replaceChildren(...optionNotes(k).map((text) => Object.assign(document.createElement("span"), { textContent: text })));
      note.style.flexDirection = "column";
    }
    const url = new URL(location.href);
    for (const k of cfg.optionKeys) {
      if (options[k] === cfg.defaults[k]) url.searchParams.delete(k);
      else url.searchParams.set(k, options[k]);
    }
    url.searchParams.set("groups", groups.join(","));
    if (measure === "rch_a") url.searchParams.delete("m"); else url.searchParams.set("m", measure);
    if (showGap) url.searchParams.delete("gap"); else url.searchParams.set("gap", "0");
    if (view === "time") url.searchParams.delete("view"); else url.searchParams.set("view", view);
    history.replaceState(null, "", url);

    // The view switch, and the controls a view doesn't use: greyed with the reason, not hidden.
    const parts = view === "parts";
    for (const b of viewButtons) b.setAttribute("aria-pressed", String(b.dataset.view === view));
    $("view-time").hidden = parts;
    $("view-parts").hidden = !parts;
    $("summary").hidden = parts;
    $("contrib-title").hidden = !parts;
    measureSel.disabled = parts;
    $("measure-reason").hidden = !parts;
    gapToggle.checked = showGap;
    gapToggle.disabled = parts || measure !== "rch_a";
    const gapReason = $("gap-reason");
    gapReason.hidden = !gapToggle.disabled;
    gapReason.textContent = t(parts ? "explore.gap_parts" : "explore.gap_annual_only");
  }

  function reasonText(r: any): string {
    const code = r.reason;
    if (code === "rule_u_end") {
      const end = cfg.availability.weights_timing.U.index[1];
      return t("reason.rule_u_end", { survey: end.slice(0, 4), month: month(L, end, "acc") });
    }
    return t(`reason.${code}`);
  }

  function optionNotes(k: string): string[] {
    if (k === "grouping") return [];
    const a = cfg.availability[k]?.[options[k]];
    if (!a) return [];
    const out = [...a.greyed, ...a.notes].map(reasonText);
    if (k === "weights_timing" && options[k] === "N") out.unshift(t("reason.timing.N"));
    return out;
  }

  // The files live on the country's data page; the link goes to the chosen setting's files there.
  function renderDownloads() {
    ($("files-this") as unknown as HTMLAnchorElement).href = `${cfg.dataPage}#setting-${slug()}`;
    const opts = [options.grouping, ...SETTING_KEYS.map((k) => t(`option.${k}.${options[k]}`))].join(", ");
    $("cite").textContent = t("explore.cite_text", { year: new Date().getFullYear(), country: cfg.country, options: opts, url: location.href });
  }

  async function render() {
    syncControls();
    renderDownloads();
    const mine = ++seq;
    $("loading").hidden = false;
    $("failed").hidden = true;
    let data: any;
    try {
      data = await load(`series/${slug()}.json`);
    } catch {
      if (mine !== seq) return;
      $("loading").hidden = true;
      $("failed").hidden = false;
      return;
    }
    if (mine !== seq) return;
    $("loading").hidden = true;
    draw(data);
    contributions();
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

  function draw(data: any) {
    const axis = axisOf(data.start, data.end);
    const field = measure === "index" ? "index" : measure;
    const lines = groups.map((g) => ({
      key: g, label: shortName(g), color: cfg.colors[g], dash: cfg.dash[g] || undefined,
      values: data.groups[dataKey(g)][field] as (number | null)[],
    }));
    const flag = data.flags[0];
    const flagTo = measure === "index" ? flag.index_to : measure === "rch_m" ? flag.rch_m_to : flag.rch_a_to;
    const flagFill = flag.code === "less certain" ? "var(--color-flag-less-certain)" : "var(--color-flag-coarser)";
    const withGap = measure === "rch_a" && showGap;
    const gapData = data.gaps[options.grouping];
    const firstIdx = Math.min(...lines.map((l) => l.values.findIndex((v) => v !== null)).filter((i) => i >= 0));
    current = {
      axis, locale: cfg.locale, unit: measure === "index" ? "" : "%",
      lines, flag: { to: flagTo, fill: flagFill }, from: axis[firstIdx],
      gap: withGap ? { values: gapData.rch_a, se: gapData.se_a, title: t("gap") } : undefined,
    };
    const chartEl = $("chart");
    const gapEl = root.querySelector<HTMLElement>(".chart-gap")!;
    $("gap-title").hidden = !withGap;
    $("gap-note").hidden = !withGap || (groups.includes("Q1") && groups.includes("Q5"));
    if (!redraw) redraw = mount(chartEl, gapEl, () => current!);
    else redraw();

    // Summary: each line's latest value.
    const ends = lines.map((l) => {
      let i = l.values.length - 1;
      while (i > 0 && l.values[i] === null) i--;
      return { g: l.key, i, v: l.values[i] as number };
    });
    const lastI = Math.max(...ends.map((e) => e.i));
    const digits = measure === "index" ? 2 : 1;
    const items = ends.map((e) => t("summary.item", { value: `${num(L, e.v, digits)}${measure === "index" ? "" : "%"}`, group: inSentence(e.g) }));
    const list = items.length > 1 ? `${items.slice(0, -1).join(", ")} ${t("summary.and")} ${items[items.length - 1]}` : items[0];
    const summary = measure === "rch_a"
      ? t("summary.annual", { month: L === "el" ? month(L, axis[lastI], "acc") : month(L, axis[lastI]), list })
      : `${t(`explore.measure.${measure}`)}, ${month(L, axis[lastI])}: ${list}.`;
    $("summary").textContent = summary;
    chartEl.setAttribute("aria-label", summary);

    // A notice when the timing rule leaves months out.
    const notice = $("notice");
    const timing = options.weights_timing;
    const notes = timing === "U" || timing === "F" ? cfg.availability.weights_timing[timing].greyed.map(reasonText) : [];
    notice.hidden = !notes.length;
    notice.querySelector("span")!.textContent = notes.join(" ");

    // Legend.
    const legend = $("legend");
    const key = (color: string, text: string, opacity = "") => {
      const s = document.createElement("span");
      s.className = "key";
      const box = document.createElement("span");
      box.className = "box";
      box.style.background = color;
      if (opacity) box.style.opacity = opacity;
      s.append(box, document.createTextNode(text));
      return s;
    };
    const parts = [key(flagFill, `${t(`flag.legend.${flag.code}`)}¹`)];
    if (withGap) parts.push(key("var(--color-text)", t("chart.band"), "0.12"), key("var(--color-disabled)", t("chart.noband")));
    legend.replaceChildren(...parts);

    // Footnotes: the flag, then each selected group's notes (once each).
    const foot: string[] = [t(`reason.${flag.code.replace(" ", "_")}`)];
    const seen = new Set<string>();
    for (const g of groups) {
      const f = data.footnotes[dataKey(g)] ?? {};
      for (const [code, v] of Object.entries<any>(f)) {
        const text = code === "hospital"
          ? `${t("reason.hospital", { first: 2008, last: 2014 })} (${v.annual_rates[0]} – ${v.annual_rates[1]})`
          : `${t(`reason.${code}`)} (${(v.index_years ?? []).join(", ")})`;
        if (!seen.has(text)) { seen.add(text); foot.push(text); }
      }
    }
    $("footnotes").replaceChildren(...foot.map((text) => Object.assign(document.createElement("li"), { textContent: text })));

    // Table.
    const tableBox = $("table");
    if (tableOpen) {
      const table = document.createElement("table");
      table.className = "data-table";
      const head = document.createElement("tr");
      for (const h of [t("chart.month"), ...groups.map(groupName), ...(withGap ? [t("gap")] : [])]) {
        head.append(Object.assign(document.createElement("th"), { scope: "col", textContent: h }));
      }
      const thead = document.createElement("thead");
      thead.append(head);
      const tbody = document.createElement("tbody");
      for (let i = axis.length - 1; i >= firstIdx; i--) {
        const tr = document.createElement("tr");
        tr.append(Object.assign(document.createElement("th"), { scope: "row", textContent: axis[i] }));
        const cells = [...lines.map((l) => l.values[i]), ...(withGap ? [gapData.rch_a[i]] : [])];
        for (const v of cells) tr.append(Object.assign(document.createElement("td"), { textContent: v === null ? "–" : num(L, v, digits) }));
        tbody.append(tr);
      }
      table.append(thead, tbody);
      tableBox.replaceChildren(table);
    }
  }

  // What made up each selected group's latest annual rate, by spending category. A group's
  // contributions add up to its rate; with exactly two groups, a difference line per category
  // (first minus second, in the page's order, as the gap chart) adds up to the gap between them,
  // and the rows are sorted by it, so the top rows explain most of the gap.
  async function contributions() {
    const box = $("contrib");
    // Without a breakdown for this setting or these groups, the view says so in words.
    const none = () => { box.hidden = true; $("contrib-none").hidden = false; $("contrib-title").textContent = ""; };
    let data: any;
    try {
      data = await load(`contributions/${slug()}.json`);
    } catch {
      none();
      return;
    }
    const shown = allGroups.filter((g) => groups.includes(g) && data.groups[dataKey(g)]);
    if (!shown.length) { none(); return; }
    const latest = (g: string) => {
      const byMonth = data.groups[dataKey(g)];
      const months = Object.keys(byMonth).sort();
      return { month: months[months.length - 1], parts: byMonth[months[months.length - 1]] as Record<string, number> };
    };
    const per = new Map(shown.map((g) => [g, latest(g)]));
    const last = [...per.values()].map((x) => x.month).sort().pop()!;
    const codes = [...new Set([...per.values()].flatMap((x) => Object.keys(x.parts)))];
    const value = (g: string, code: string): number | null => per.get(g)!.parts[code] ?? null;
    const total = (g: string) => Object.values(per.get(g)!.parts).reduce((a, v) => a + v, 0);
    const pair = shown.length === 2 ? shown : null;
    const diff = (code: string): number | null => {
      if (!pair) return null;
      const a = value(pair[0], code), b = value(pair[1], code);
      return a === null || b === null ? null : a - b;
    };
    const size = (code: string) => pair
      ? Math.abs(diff(code) ?? 0)
      : Math.max(...shown.map((g) => Math.abs(value(g, code) ?? 0)));
    codes.sort((a, b) => size(b) - size(a) || a.localeCompare(b));

    // One scale for every bar, so lengths compare across groups and categories.
    const all = codes.flatMap((c) => [...shown.map((g) => value(g, c)), diff(c)]).filter((v): v is number => v !== null);
    const pos = Math.max(0, ...all), neg = Math.max(0, ...all.map((v) => -v));
    const span = Math.max(pos + neg, 0.01);
    const zero = (neg / span) * 100;
    // Rounded before the sign, so a sum that is zero up to float noise shows as 0.00, not +0.00.
    const signed = (v: number) => {
      const r = Math.round(v * 100) / 100;
      return `${r > 0 ? "+" : r < 0 ? "−" : ""}${num(L, Math.abs(r), 2)}`;
    };
    const bar = (v: number | null, color: string) => {
      const track = document.createElement("div");
      track.className = "track";
      if (v !== null) {
        const fillEl = document.createElement("div");
        fillEl.className = "fill";
        const w = (Math.abs(v) / span) * 100;
        fillEl.style.left = `${v < 0 ? zero - w : zero}%`;
        fillEl.style.width = `${w}%`;
        fillEl.style.background = color;
        track.append(fillEl);
      }
      if (neg > 0) {
        const z = document.createElement("div");
        z.className = "zero";
        z.style.left = `${zero}%`;
        track.append(z);
      }
      return track;
    };
    const textSpan = (cls: string, text: string) => Object.assign(document.createElement("span"), { className: cls, textContent: text });
    const swatch = (g: string) => {
      const ns = "http://www.w3.org/2000/svg";
      const svg = document.createElementNS(ns, "svg");
      svg.setAttribute("width", "16"); svg.setAttribute("height", "8"); svg.setAttribute("viewBox", "0 0 16 8"); svg.setAttribute("aria-hidden", "true");
      const line = document.createElementNS(ns, "line");
      for (const [k, v] of Object.entries({ x1: "1", y1: "4", x2: "15", y2: "4", stroke: cfg.colors[g], "stroke-width": "2.5", "stroke-linecap": "round" })) line.setAttribute(k, v);
      if (cfg.dash[g]) line.setAttribute("stroke-dasharray", cfg.dash[g]);
      svg.append(line);
      return svg;
    };
    // Totals are an order of magnitude larger than any category, so they get no bar.
    const line = (name: Node[], v: number | null, color: string, cls = "", withBar = true) => {
      const row = document.createElement("div");
      row.className = `contrib-line ${cls}`.trim();
      const label = document.createElement("span");
      label.className = "name";
      label.append(...name);
      row.append(label, withBar ? bar(v, color) : document.createElement("span"), textSpan("v", v === null ? "–" : signed(v)));
      return row;
    };

    box.hidden = false;
    $("contrib-none").hidden = true;
    $("contrib-title").textContent = shown.length === 1
      ? t("explore.contrib_title", { group: inSentence(shown[0]), value: `${num(L, total(shown[0]))}%` })
      : t("explore.contrib_title_many");
    const notes = [t("explore.contrib_note", { month: month(L, last) }), t("explore.contrib_sum")];
    if (pair) {
      const gap = total(pair[0]) - total(pair[1]);
      notes.push(t("explore.contrib_diff_note", { a: inSentence(pair[0]), b: inSentence(pair[1]), gap: signed(gap) }));
    }
    $("contrib-note").textContent = notes.join(" ");

    if (shown.length === 1) {
      const g = shown[0];
      const rows = codes.map((code) => {
        const row = line([document.createTextNode(cfg.divisions[code] ?? code)], value(g, code), cfg.colors[g]);
        row.classList.add("single");
        return row;
      });
      $("bars").replaceChildren(...rows);
      fold(rows);
      return;
    }
    const nameOf = (g: string) => [swatch(g), document.createTextNode(shortName(g))];
    const diffName = () => [document.createTextNode(t("explore.contrib_diff"))];
    const block = (title: string, lines: HTMLElement[]) => {
      const b = document.createElement("div");
      b.className = "contrib-row";
      b.append(textSpan("label", title), ...lines);
      return b;
    };
    const rows = codes.map((code) => block(cfg.divisions[code] ?? code, [
      ...shown.map((g) => line(nameOf(g), value(g, code), cfg.colors[g])),
      ...(pair ? [line(diffName(), diff(code), "var(--color-text-muted)", "diff")] : []),
    ]));
    const totals = block(t("explore.contrib_total"), [
      ...shown.map((g) => line(nameOf(g), total(g), cfg.colors[g], "", false)),
      ...(pair ? [line(diffName(), total(pair[0]) - total(pair[1]), "var(--color-text-muted)", "diff", false)] : []),
    ]);
    totals.classList.add("total");
    $("bars").replaceChildren(...rows, totals);
    fold(rows);
  }

  // The breakdown shows the largest categories first (rows are sorted by size) and folds the rest
  // behind one button, so the page stays short until a reader asks for all of it. The choice holds
  // while groups and options change.
  const TOP = 5;
  let showAll = false;
  let folded: HTMLElement[] = [];
  function fold(rows: HTMLElement[]) {
    folded = rows;
    const more = $("contrib-more");
    rows.forEach((r, i) => { r.hidden = !showAll && i >= TOP; });
    more.hidden = rows.length <= TOP;
    more.textContent = showAll ? t("explore.contrib_fewer", { n: TOP }) : t("explore.contrib_all", { n: rows.length });
    more.setAttribute("aria-expanded", String(showAll));
  }
  $("contrib-more").addEventListener("click", () => { showAll = !showAll; fold(folded); });

  render();
}
