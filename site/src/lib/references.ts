// The bibliography, formatted for the page. Pages cite sources by key; an unknown key stops the
// build, so no published number goes out without the sources it relies on.

import { readJson } from "./data";

export interface Reference {
  entrytype: string;
  author: string;
  title: string;
  date?: string;
  journaltitle?: string;
  volume?: string;
  number?: string;
  pages?: string;
  publisher?: string;
  institution?: string;
  edition?: string;
  series?: string;
  doi?: string;
  url?: string;
  type?: string;
}

let cache: Record<string, Reference> | null = null;

export function references(): Record<string, Reference> {
  cache ??= readJson<{ references: Record<string, Reference> }>("references.json").references;
  return cache;
}

export function reference(key: string): Reference {
  const r = references()[key];
  if (!r) throw new Error(`unknown bibliography key "${key}"`);
  return r;
}

/** Parts of a formatted reference: text, the title (italic for books, manuals, reports, data),
 *  and a link (DOI first). */
export function format(key: string, lang: "el" | "en"): { lead: string; title: string; italic: boolean; rest: string; link?: { href: string; text: string } } {
  const r = reference(key);
  const year = r.date ? ` (${r.date.slice(0, 4)})` : "";
  const italic = ["book", "manual", "report", "dataset", "software", "online"].includes(r.entrytype);
  const parts: string[] = [];
  if (r.journaltitle) {
    let j = r.journaltitle;
    if (r.volume) j += ` ${r.volume}`;
    if (r.number && r.entrytype === "article") j += r.volume ? `(${r.number})` : ` ${r.number}`;
    if (r.pages) j += `: ${r.pages}`;
    parts.push(j);
  }
  if (r.edition && r.entrytype !== "article") parts.push(lang === "el" ? `έκδοση ${r.edition}` : `${r.edition} edition`);
  if (r.series) parts.push(r.series);
  if (r.number && r.entrytype !== "article") parts.push(r.number);
  if (r.publisher) parts.push(r.publisher);
  if (r.institution) parts.push(r.institution);
  const link = r.doi ? { href: `https://doi.org/${r.doi}`, text: `doi:${r.doi}` } : r.url ? { href: r.url, text: new URL(r.url).hostname } : undefined;
  return { lead: `${r.author}${year}.`, title: r.title, italic, rest: parts.length ? `${parts.join(". ")}.` : "", link };
}
