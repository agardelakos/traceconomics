// The calculator page: presets, sliders and the result, using the tested engine. Nothing leaves
// the device: there is no form, no request with the visitor's numbers, no storage.

import { annualRate, chain, divisionShares, presetWeights, published, type CalculatorData, type Shares } from "../lib/engine/calculator";
import { roundHalfEven } from "../lib/engine/round";
import { fill, month, num, type Lang } from "../lib/format";
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
  let preset = presetSel.value;
  let shares: Shares | null = null;          // null: untouched, the preset as published
  let touched = false;

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
    const mine = shares ? published(chain(data, preset, shares)) : base;
    const p = lastMonth(base);
    const yours = rate(mine, p);
    const theirs = rate(base, p);
    const edited = shares !== null;
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
    reset.textContent = t("calc.reset", { preset: name(preset) });
    $("rescaled").hidden = !(edited && touched);

    // Sliders: the shares in use (the preset's newest year when untouched).
    const s = shares ?? presetShares();
    const ref = presetShares();
    const box = $("sliders");
    if (!box.childElementCount) build(box);
    for (const [d, input] of inputs) {
      const v = (s[d] ?? 0) * 100;
      input.value = v.toFixed(1);
      input.setAttribute("aria-valuetext", `${num(L, v)}%`);
      values.get(d)!.textContent = `${num(L, v)}%`;
      const changed = Math.abs((s[d] ?? 0) - (ref[d] ?? 0)) > 5e-4;
      notes.get(d)!.textContent = changed ? t("calc.changed", { value: `${num(L, (ref[d] ?? 0) * 100)}%` }) : t("calc.as_preset");
      notes.get(d)!.classList.toggle("muted", !changed);
    }

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

  /** One division to `v`; the others scaled in proportion so the shares still sum to 1. */
  function set(d: string, v: number) {
    const cur = { ...(shares ?? presetShares()) };
    const others = Object.entries(cur).filter(([k]) => k !== d).reduce((a, [, x]) => a + x, 0);
    const scale = others > 0 ? (1 - v) / others : 0;
    const next: Shares = {};
    for (const k of Object.keys(cfg.divisions)) next[k] = k === d ? v : (cur[k] ?? 0) * scale;
    shares = next;
    touched = true;
    render();
  }

  presetSel.addEventListener("change", () => { preset = presetSel.value; shares = null; touched = false; render(); });
  $("reset").addEventListener("click", () => { shares = null; touched = false; render(); });
  render();
}
