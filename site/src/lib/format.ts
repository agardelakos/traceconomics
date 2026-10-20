// Months and numbers in each site language, shared by the pages (at build time) and the scripts
// (in the browser). No text files are imported here, so scripts stay small.

export type Lang = "el" | "en";
export const LOCALE: Record<Lang, string> = { el: "el-GR", en: "en-GB" };

/** A published number as the reader's language writes it (5,1 or 5.1). Negative zero shows as 0. */
export function num(lang: Lang, value: number, digits = 1): string {
  return new Intl.NumberFormat(LOCALE[lang], {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
    signDisplay: "negative",
  }).format(value);
}

export const pct = (lang: Lang, value: number, digits = 1) => `${num(lang, value, digits)}%`;

// Greek uses the accusative after "τον" ("τον Σεπτέμβριο 2026"), which Intl doesn't provide.
const EL_MONTHS = {
  nom: ["Ιανουάριος", "Φεβρουάριος", "Μάρτιος", "Απρίλιος", "Μάιος", "Ιούνιος", "Ιούλιος", "Αύγουστος", "Σεπτέμβριος", "Οκτώβριος", "Νοέμβριος", "Δεκέμβριος"],
  acc: ["Ιανουάριο", "Φεβρουάριο", "Μάρτιο", "Απρίλιο", "Μάιο", "Ιούνιο", "Ιούλιο", "Αύγουστο", "Σεπτέμβριο", "Οκτώβριο", "Νοέμβριο", "Δεκέμβριο"],
};
const EN_MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];

/** "September 2026" / "Σεπτέμβριος 2026"; `form: "acc"` for Greek after "τον". */
export function month(lang: Lang, period: string, form: "nom" | "acc" = "nom"): string {
  const y = period.slice(0, 4);
  const m = Number(period.slice(5, 7)) - 1;
  return `${lang === "el" ? EL_MONTHS[form][m] : EN_MONTHS[m]} ${y}`;
}

/** Fill {name} slots in a text. A missing value is an error, never an empty gap. */
export function fill(text: string, vars: Record<string, string | number> = {}): string {
  return text.replace(/\{(\w+)\}/g, (_, name) => {
    if (!(name in vars)) throw new Error(`text "${text.slice(0, 40)}…" needs {${name}}`);
    return String(vars[name]);
  });
}
