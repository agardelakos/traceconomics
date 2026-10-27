// Who is in each income fifth, in euros, for a given household.
//
// The fifths rank people by equivalised income: the household's net income divided by its size
// on the modified OECD scale (1 for the first person aged 14 or over, 0.5 for each other person
// aged 14 or over, 0.3 for each child under 14). A cut-off is therefore per "adult equivalent";
// a household's own limit is the cut-off times its size. Shared by the page (at build time) and
// the panel's script (in the browser), so nothing here imports text files.

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

// Amounts are written one way on every page, in both languages: a point before the decimals and a
// narrow no-break space between thousands ("€130.8", "€14 931", "8 272 PPS"). The space is the SI
// and EU style convention, and the only mark read the same way in both languages: a comma or a
// point there would be read the other way round in one of them.
function digits3(value: number, digits: number): string {
  const [whole, frac] = Math.abs(value).toFixed(digits).split(".");
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, "\u202f");
  const sign = value < 0 && Number(value.toFixed(digits)) !== 0 ? "−" : "";
  return `${sign}${grouped}${frac ? `.${frac}` : ""}`;
}

/** Euros, the sign first: "€130.8". */
export function eur(value: number, digits = 0): string {
  const n = digits3(value, digits);
  return n.startsWith("−") ? `−€${n.slice(1)}` : `€${n}`;
}

/** Purchasing power standards, the unit after the number as Eurostat writes it: "8 272 PPS". */
export function pps(value: number, digits = 0): string {
  return `${digits3(value, digits)}\u00a0PPS`;
}

export type Unit = "eur" | "pps";
export const amount = (unit: Unit, value: number) => (unit === "pps" ? pps(value) : eur(value));

/** How close to a limit an income can be before the finder says it could be in either fifth: 5%,
 *  a little more than the measured gap between the two surveys' income definitions (about 4% on
 *  the poorest fifth's line). A plain warning, not a statistical margin. */
export const NEAR_LIMIT = 0.05;

export interface Placement {
  fifth: (typeof FIFTHS)[number];
  /** The fifth on the other side of a limit within NEAR_LIMIT, if any. */
  neighbour: (typeof FIFTHS)[number] | null;
}

/** Which fifth a household's yearly net income puts it in, for a household of the given size.
 *  An income exactly at a top cut-off belongs to that fifth ("up to"). */
export function placeIncome(topCutoffs: Record<string, number>, size: number, yearly: number): Placement {
  if (!(yearly >= 0) || !(size > 0)) throw new Error(`no placement for an income of ${yearly} and a size of ${size}`);
  const cuts = FIFTHS.slice(0, 4).map((q) => {
    const c = topCutoffs[q];
    if (typeof c !== "number") throw new Error(`no cut-off for ${q}`);
    return c;
  });
  const equivalised = yearly / size;
  const i = cuts.findIndex((c) => equivalised <= c);
  const at = i === -1 ? 4 : i;
  // The nearest limit: this fifth's top or its bottom, whichever is closer.
  const near = [at - 1, at]
    .filter((k) => k >= 0 && k < 4)
    .map((k) => ({ k, d: Math.abs(equivalised - cuts[k]) / cuts[k] }))
    .filter((x) => x.d <= NEAR_LIMIT)
    .sort((a, b) => a.d - b.d)[0];
  const neighbour = near === undefined ? null : FIFTHS[near.k === at ? at + 1 : at - 1];
  return { fifth: FIFTHS[at], neighbour };
}

/** A euro amount as a reader types it, in either language: "1500", "1 500", "1.500", "1,500",
 *  "45,50", "45.5", with or without "€". A separator followed by three digits groups thousands;
 *  one followed by one or two digits at the end starts the cents, and must differ from the
 *  thousands mark if there is one. Anything else is null. */
export function parseAmount(text: string): number | null {
  const s = text.replace(/[\s€]/g, "");   // \s includes the no-break and narrow no-break spaces
  const m = /^(\d{1,3}(?:([.,])\d{3})(?:\2\d{3})*|\d+)(?:([.,])(\d{1,2}))?$/.exec(s);
  if (!m || (m[2] && m[3] === m[2])) return null;
  return Number(m[1].replace(/[.,]/g, "")) + (m[4] ? Number(`0.${m[4]}`) : 0);
}
