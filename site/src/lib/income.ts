// Who is in each income fifth, in euros, for a given household.
//
// The fifths rank people by equivalised income: the household's net income divided by its size
// on the modified OECD scale (1 for the first person aged 14 or over, 0.5 for each other person
// aged 14 or over, 0.3 for each child under 14). A cut-off is therefore per "adult equivalent";
// a household's own limit is the cut-off times its size. Shared by the page (at build time) and
// the panel's script (in the browser), so nothing here imports text files.

import { num, type Lang } from "./format";

export const FIFTHS = ["Q1", "Q2", "Q3", "Q4", "Q5"] as const;

/** The household types offered, with their people aged 14 or over and children under 14. */
export const HOUSEHOLD_TYPES = [
  { key: "one", older: 1, children: 0 },
  { key: "two", older: 2, children: 0 },
  { key: "two_child", older: 2, children: 1 },
  { key: "two_children", older: 2, children: 2 },
  { key: "one_child", older: 1, children: 1 },
  { key: "three", older: 3, children: 0 },
] as const;

/** Size on the modified OECD scale. A household always has someone aged 14 or over to count 1. */
export function equivalentSize(older: number, children: number): number {
  if (!Number.isInteger(older) || !Number.isInteger(children) || older < 1 || children < 0) {
    throw new Error(`no household of ${older} people aged 14 or over and ${children} children`);
  }
  // Tenths, so 1.8 stays 1.8 and not 1.7999999999999998.
  return Math.round(10 + 5 * (older - 1) + 3 * children) / 10;
}

export interface Range { from: number | null; to: number | null }

/** Each fifth's yearly net income range for a household of the given size. The richest fifth has
 *  no upper limit and the poorest no lower one. Euros, rounded to whole euros. */
export function ranges(topCutoffs: Record<string, number>, size: number): Range[] {
  const cut = FIFTHS.slice(0, 4).map((q) => {
    const c = topCutoffs[q];
    if (typeof c !== "number") throw new Error(`no cut-off for ${q}`);
    return c * size;
  });
  return FIFTHS.map((_, i) => ({
    from: i === 0 ? null : Math.round(cut[i - 1]),
    to: i === 4 ? null : Math.round(cut[i]),
  }));
}

/** "€7,110" in English, "7.110 €" in Greek. */
export function eur(lang: Lang, value: number): string {
  const n = num(lang, value, 0);
  return lang === "el" ? `${n} €` : `€${n}`;
}
