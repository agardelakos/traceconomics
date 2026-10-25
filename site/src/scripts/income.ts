// The "who is in each income fifth" panel on Explore: redraws the euro ranges for the household
// the reader picks. The page already shows one adult's ranges, so without scripts it still says
// something true.

import { fill, num, type Lang } from "../lib/format";
import { equivalentSize, eur, FIFTHS, ranges, type Range } from "../lib/income";

interface Config {
  lang: Lang;
  cutoffs: Record<string, number>;
  types: Record<string, [number, number]>;
  text: Record<string, string>;
}

export function startIncome(root: HTMLElement): void {
  const cfg: Config = JSON.parse(root.dataset.income!);
  const other = root.querySelector<HTMLElement>('[data-income-role="other"]')!;
  const sizeNote = root.querySelector<HTMLElement>('[data-income-role="size"]')!;
  const older = root.querySelector<HTMLInputElement>('input[name="older"]')!;
  const children = root.querySelector<HTMLInputElement>('input[name="children"]')!;

  const text = (r: Range, per: "year" | "month") => {
    const d = per === "year" ? 1 : 12;
    if (r.from === null) return fill(cfg.text[`${per}.upto`], { amount: eur(cfg.lang, r.to! / d) });
    if (r.to === null) return fill(cfg.text[`${per}.over`], { amount: eur(cfg.lang, r.from / d) });
    return fill(cfg.text[`${per}.between`], { from: eur(cfg.lang, r.from / d), to: eur(cfg.lang, r.to / d) });
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
    const rows = ranges(cfg.cutoffs, size);
    FIFTHS.forEach((q, i) => {
      root.querySelector(`[data-income-year="${q}"]`)!.textContent = text(rows[i], "year");
      root.querySelector(`[data-income-month="${q}"]`)!.textContent = text(rows[i], "month");
    });
  };

  root.addEventListener("change", draw);
  root.addEventListener("input", (e) => { if ((e.target as HTMLElement).matches('input[type="number"]')) draw(); });
  draw();
}
