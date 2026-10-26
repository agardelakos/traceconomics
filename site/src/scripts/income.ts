// The "who is in each income fifth" panel on Explore: redraws the ranges for the household and
// the unit (euros or purchasing power standards) the reader picks. The page already shows one
// adult's ranges in euros, so without scripts it still says something true.

import { fill, num, type Lang } from "../lib/format";
import { amount, equivalentSize, FIFTHS, ranges, type Range, type Unit } from "../lib/income";

interface Config {
  lang: Lang;
  cutoffs: Record<Unit, Record<string, number>>;
  types: Record<string, [number, number]>;
  text: Record<string, string>;
}

export function startIncome(root: HTMLElement): void {
  const cfg: Config = JSON.parse(root.dataset.income!);
  const other = root.querySelector<HTMLElement>('[data-income-role="other"]')!;
  const sizeNote = root.querySelector<HTMLElement>('[data-income-role="size"]')!;
  const older = root.querySelector<HTMLInputElement>('input[name="older"]')!;
  const children = root.querySelector<HTMLInputElement>('input[name="children"]')!;

  const text = (r: Range, per: "year" | "month", unit: Unit) => {
    const d = per === "year" ? 1 : 12;
    const a = (v: number) => amount(unit, v / d);
    if (r.from === null) return fill(cfg.text[`${per}.upto`], { amount: a(r.to!) });
    if (r.to === null) return fill(cfg.text[`${per}.over`], { amount: a(r.from) });
    return fill(cfg.text[`${per}.between`], { from: a(r.from), to: a(r.to) });
  };

  // A number box the reader is still typing in may be empty or out of range: keep it within
  // bounds for the sums, and leave the box itself alone.
  const count = (input: HTMLInputElement, lo: number) => {
    const v = Math.round(Number(input.value));
    return Number.isFinite(v) ? Math.min(Math.max(v, lo), Number(input.max)) : lo;
  };

  const draw = () => {
    const picked = root.querySelector<HTMLInputElement>('input[name="household"]:checked')?.value ?? "one";
    other.hidden = picked !== "other";
    const [o, c] = picked === "other" ? [count(older, 1), count(children, 0)] : cfg.types[picked];
    const size = equivalentSize(o, c);
    sizeNote.textContent = fill(cfg.text.size, { size: num(cfg.lang, size) });
    const unit = (root.querySelector<HTMLInputElement>('input[name="income-unit"]:checked')?.value ?? "eur") as Unit;
    const rows = ranges(cfg.cutoffs[unit], size);
    FIFTHS.forEach((q, i) => {
      root.querySelector(`[data-income-year="${q}"]`)!.textContent = text(rows[i], "year", unit);
      root.querySelector(`[data-income-month="${q}"]`)!.textContent = text(rows[i], "month", unit);
    });
  };

  root.addEventListener("change", draw);
  root.addEventListener("input", (e) => { if ((e.target as HTMLElement).matches('input[type="number"]')) draw(); });
  draw();
}
