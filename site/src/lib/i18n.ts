// Interface text in each site language, for pages at build time.
//
// Every label is a key in the language files (src/i18n/<lang>.json); a missing key is an error,
// never a silent fallback to the other language. Numbers and months: `format.ts`.

import el from "../i18n/el.json";
import en from "../i18n/en.json";
import { fill, type Lang } from "./format";

export { LOCALE, month, num, pct, type Lang } from "./format";

export const LANGS = ["el", "en"] as const;

const STRINGS: Record<Lang, Record<string, string>> = { el, en };

export function t(lang: Lang, key: string, vars: Record<string, string | number> = {}): string {
  const text = STRINGS[lang][key];
  if (text === undefined) throw new Error(`missing text "${key}" for ${lang}`);
  return fill(text, vars);
}

export function has(lang: Lang, key: string): boolean {
  return key in STRINGS[lang];
}

export function otherLang(lang: Lang): Lang {
  return lang === "el" ? "en" : "el";
}

/** A page's address in a language: /el/explore/ and so on. */
export function href(lang: Lang, path = ""): string {
  const clean = path.replace(/^\/+|\/+$/g, "");
  return clean ? `/${lang}/${clean}/` : `/${lang}/`;
}
