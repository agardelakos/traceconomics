// The calculator page: the starting group, the reader's spending and the result, using the tested
// engine. Spending is set as shares (sliders) or as euros a month per category, which become
// shares here. Nothing leaves the device: there is no form, no request with the visitor's numbers,
// no storage, and the address carries at most the starting group (as the group finder links it).

import { annualRate, chain, divisionShares, presetWeights, published, type CalculatorData, type Shares } from "../lib/engine/calculator";
import { roundHalfEven } from "../lib/engine/round";
import { fill, month, num, type Lang } from "../lib/format";
import { eur, parseAmount } from "../lib/income";
import { mount, type ChartSpec } from "./chart";

interface Config {
  lang: Lang;
  locale: string;
  src: string;
  presets: { key: string; name: string }[];
  divisions: Record<string, string>;
  strings: Record<string, string>;
}

const SLIDER_MAX = 60;           // percent of spending one category can take on the slider

export async function start(root: HTMLElement): Promise<void> {
  const cfg: Config = JSON.parse(root.dataset.config ?? "{}");
  const L = cfg.lang;
  const t = (key: string, vars: Record<string, string | number> = {}) => {
    const text = cfg.strings[key];
    if (text === undefined) throw new Error(`missing text "${key}"`);
    return fill(text, vars);
  };
  const $ = <T extends HTMLElement>(role: string) => root.querySelector<T>(`[data-role="${role}"]`)!;

  let data: CalculatorData;
  try {
    const res = await fetch(cfg.src);
    if (!res.ok) throw new Error(String(res.status));
    data = await res.json();
  } catch {
    $("loading").replaceChildren(Object.assign(document.createElement("strong"), { textContent: t("chart.failed") }));
    return;
  }
  $("loading").hidden = true;
  for (const role of ["result", "sliders-box", "over-time"]) $(role).hidden = false;

  const presetSel = $<HTMLSelectElement>("preset");
  const asked = new URLSearchParams(location.search).get("from");
  if (asked && cfg.presets.some((p) => p.key === asked)) presetSel.value = asked;
  let preset = presetSel.value;
  let mode: "shares" | "euros" = "shares";
  let shares: Shares | null = null;          // shares mode; null: untouched, the preset as published
  let touched = false;
  const moved = new Set<string>();           // categories the reader set, not rescaled ones
  const euros = new Map<string, number>();   // euros mode: the amounts entered, by category

  /** The euros as shares, or null while nothing is entered. An empty category counts as zero. */
  function euroShares(): Shares | null {
    const total = [...euros.values()].reduce((a, v) => a + v, 0);
    if (!(total > 0)) return null;
    return Object.fromEntries(Object.keys(cfg.divisions).map((d) => [d, (euros.get(d) ?? 0) / total]));
  }
  const inUse = () => (mode === "euros" ? euroShares() : shares);

  const official = new Map<string, Map<string, number>>();
  const officialIndex = (p: string) => {
    if (!official.has(p)) official.set(p, published(chain(data, p)));
    return official.get(p)!;
  };
  const lastYear = () => Math.max(...Object.keys(data.presets[preset]).map(Number));
  const presetShares = () => divisionShares(presetWeights(data, preset).get(lastYear())!);
  const name = (p: string) => cfg.presets.find((x) => x.key === p)!.name;

  function lastMonth(idx: Map<string, number>): string {
    return [...idx.keys()].sort().at(-1)!;
  }
  const rate = (idx: Map<string, number>, p: string) => roundHalfEven(annualRate(idx, p)!, 1);

  let redraw: (() => void) | null = null;
  let spec: ChartSpec | null = null;

  function render() {
    const base = officialIndex(preset);
    const used = inUse();
    const mine = used ? published(chain(data, preset, used)) : base;
    const p = lastMonth(base);
    const yours = rate(mine, p);
    const theirs = rate(base, p);
    const edited = used !== null;
    $("yours-label").textContent = t("calc.yours", { month: month(L, p) });
    $("yours").textContent = `${num(L, yours)}%`;
    $("same").hidden = edited;
    $("same").textContent = t("calc.same", { preset: name(preset) });
    const diff = $("diff");
    diff.hidden = !edited;
    if (edited) {
      const d = roundHalfEven(yours - theirs, 1);
      diff.textContent = t(d >= 0 ? "calc.diff_up" : "calc.diff_down", { points: num(L, Math.abs(d)), preset: name(preset) });
    }
    $("result").classList.toggle("edited", edited);
    $("preset-name").textContent = name(preset);
    $("preset-rate").textContent = `${num(L, theirs)}%`;
    $("all-rate").textContent = `${num(L, rate(officialIndex("all/all"), p))}%`;
    const reset = $<HTMLButtonElement>("reset");
    reset.hidden = !edited;
    reset.textContent = mode === "euros" ? t("calc.euros.clear") : t("calc.reset", { preset: name(preset) });
    $("rescaled").hidden = !(mode === "shares" && edited && touched);
    $("sticky").textContent = t("calc.sticky", { rate: `${num(L, yours)}%`, preset: name(preset), theirs: `${num(L, theirs)}%` });

    // The two ways in: one pane shown, the switch saying which.
    $("pane-shares").hidden = mode !== "shares";
    $("pane-euros").hidden = mode !== "euros";
    for (const b of root.querySelectorAll<HTMLButtonElement>("[data-mode]")) b.setAttribute("aria-pressed", String(b.dataset.mode === mode));

    // Sliders: the shares in use (the preset's newest year when untouched). A category that moved
    // only because another one did says so.
    const s = used ?? presetShares();
    const ref = presetShares();
    const box = $("sliders");
    if (!box.childElementCount) build(box);
    for (const [d, input] of inputs) {
      const v = (s[d] ?? 0) * 100;
      input.value = v.toFixed(1);
      input.setAttribute("aria-valuetext", `${num(L, v)}%`);
      values.get(d)!.textContent = `${num(L, v)}%`;
      const changed = Math.abs((s[d] ?? 0) - (ref[d] ?? 0)) > 5e-4;
      const was = { value: `${num(L, (ref[d] ?? 0) * 100)}%` };
      notes.get(d)!.textContent = !changed ? t("calc.as_preset") : moved.has(d) ? t("calc.changed", was) : t("calc.adjusted", was);
      notes.get(d)!.classList.toggle("muted", !changed);
    }

    // Euros: each category's share of the total, and the total.
    const grid = $("euros");
    if (!grid.childElementCount) buildEuros(grid);
    const total = [...euros.values()].reduce((a, v) => a + v, 0);
    for (const [d, out] of euroShareOut) {
      const amount = euros.get(d);
      out.textContent = invalid.has(d) ? t("calc.euros.invalid") : amount !== undefined && total > 0 ? t("calc.euros.share", { share: `${num(L, (100 * amount) / total)}%` }) : "";
    }
    $("euros-total").textContent = t("calc.euros.total", { amount: eur(total, Number.isInteger(total) ? 0 : 2) });
    $("euros-empty").hidden = total > 0;

    // Over time: the preset's annual rate and, once changed, yours.
    const axis = [...base.keys()].sort();
    const series = (idx: Map<string, number>) => axis.map((m) => annualRate(idx, m)).map((v) => (v === null ? null : roundHalfEven(v, 1)));
    spec = {
      axis, locale: cfg.locale, unit: "%",
      lines: [
        { key: "preset", label: name(preset), color: "var(--series-all)", values: series(base) },
        ...(edited ? [{ key: "yours", label: t("calc.title"), color: "var(--series-q1)", values: series(mine) }] : []),
      ],
      from: axis[12],
    };
    $("chart").setAttribute("aria-label", `${t("calc.over_time")}: ${spec.lines.map((l) => l.label).join(", ")}`);
    if (!redraw) redraw = mount($("chart"), null, () => spec!);
    else redraw();
  }

  const inputs = new Map<string, HTMLInputElement>();
  const values = new Map<string, HTMLElement>();
  const notes = new Map<string, HTMLElement>();

  function build(box: HTMLElement) {
    for (const d of Object.keys(cfg.divisions).sort()) {
      const row = document.createElement("div");
      row.className = "slider-row";
      const top = document.createElement("div");
      top.className = "top";
      const label = Object.assign(document.createElement("label"), { htmlFor: `div-${d}`, textContent: cfg.divisions[d] });
      const value = Object.assign(document.createElement("span"), { className: "num", style: "font-weight: 700; white-space: nowrap" });
      top.append(label, value);
      const input = Object.assign(document.createElement("input"), { type: "range", id: `div-${d}`, min: "0", max: String(SLIDER_MAX), step: "0.1" });
      input.addEventListener("input", () => set(d, Number(input.value) / 100));
      const note = Object.assign(document.createElement("span"), { className: "small" });
      row.append(top, input, note);
      box.append(row);
      inputs.set(d, input);
      values.set(d, value);
      notes.set(d, note);
    }
  }

  const euroInputs = new Map<string, HTMLInputElement>();
  const euroShareOut = new Map<string, HTMLElement>();
  const invalid = new Set<string>();

  function buildEuros(grid: HTMLElement) {
    for (const d of Object.keys(cfg.divisions).sort()) {
      const row = document.createElement("div");
      row.className = "euro-row";
      const label = Object.assign(document.createElement("label"), { htmlFor: `eur-${d}`, textContent: cfg.divisions[d] });
      const input = Object.assign(document.createElement("input"), { type: "text", id: `eur-${d}`, inputMode: "decimal", autocomplete: "off", placeholder: "€" });
      input.setAttribute("aria-label", t("calc.euros.input", { category: cfg.divisions[d] }));
      const out = Object.assign(document.createElement("span"), { className: "small muted", id: `eur-${d}-share` });
      input.setAttribute("aria-describedby", out.id);
      input.addEventListener("input", () => {
        const text = input.value.trim();
        const v = text === "" ? null : parseAmount(text);
        invalid.delete(d);
        euros.delete(d);
        if (text !== "" && v === null) invalid.add(d);
        else if (v !== null) euros.set(d, v);
        input.toggleAttribute("aria-invalid", invalid.has(d));
        render();
      });
      row.append(label, input, out);
      grid.append(row);
      euroInputs.set(d, input);
      euroShareOut.set(d, out);
    }
  }

  /** One division to `v`; the others scaled in proportion so the shares still sum to 1. */
  function set(d: string, v: number) {
    const cur = { ...(shares ?? presetShares()) };
    const others = Object.entries(cur).filter(([k]) => k !== d).reduce((a, [, x]) => a + x, 0);
    const scale = others > 0 ? (1 - v) / others : 0;
    const next: Shares = {};
    for (const k of Object.keys(cfg.divisions)) next[k] = k === d ? v : (cur[k] ?? 0) * scale;
    shares = next;
    touched = true;
    moved.add(d);
    render();
  }

  function clearShares() { shares = null; touched = false; moved.clear(); }
  function clearEuros() {
    euros.clear();
    invalid.clear();
    for (const input of euroInputs.values()) { input.value = ""; input.removeAttribute("aria-invalid"); }
  }

  // A new starting group resets the sliders (they were that group's shares); amounts in euros are
  // the reader's own and stay, the group then gives only each category's inner mix.
  presetSel.addEventListener("change", () => {
    preset = presetSel.value;
    if (mode === "shares") clearShares();
    const u = new URL(location.href);
    u.searchParams.set("from", preset);
    history.replaceState(null, "", u);
    render();
  });
  $("reset").addEventListener("click", () => { if (mode === "euros") clearEuros(); else clearShares(); render(); });
  // From euros to shares, the sliders start from the shares the euros gave, every one the
  // reader's own (an empty category was set to nothing spent).
  for (const b of root.querySelectorAll<HTMLButtonElement>("[data-mode]")) {
    b.addEventListener("click", () => {
      const next = b.dataset.mode as "shares" | "euros";
      if (next === mode) return;
      const fromEuros = euroShares();
      if (next === "shares" && fromEuros) {
        shares = fromEuros;
        touched = false;
        moved.clear();
        for (const d of Object.keys(cfg.divisions)) moved.add(d);
      }
      mode = next;
      render();
    });
  }
  render();
}
