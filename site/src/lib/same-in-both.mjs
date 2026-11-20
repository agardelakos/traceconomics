// Figures that read the same whatever the data. Pages put the numbers they show into the HTML at
// build time, from the release's data files. A figure typed into a component or a page template
// instead doesn't follow the data, and the text check (quoted-figures.mjs, site check 11) can't see
// it: it reads only the interface strings and the content pages.
//
// So the site is built twice, on two made-up data sets with the same pages and other numbers
// (tests/sitedata.py --values a|b), and each page's figures are compared, place by place. A figure
// that reads the same in both builds and isn't typed in the text is listed: it came from somewhere
// other than the data. A figure listed in src/i18n/same-in-both-allow.json, with its reason, is a
// constant the pages may show (none so far).
//
// Plain JavaScript, like quoted-figures.mjs, whose figure pattern it uses.

import fs from "node:fs";
import path from "node:path";
import { figuresIn } from "./quoted-figures.mjs";

const ENTITIES = { amp: "&", lt: "<", gt: ">", quot: '"', "#39": "'", nbsp: " ", "#160": " " };

/** What a reader sees or hears on a page: its text (scripts and styles left out), and its
 * aria-label and title attributes, which screen readers read out. */
export function pageText(html) {
  const decode = (s) => s.replace(/&(amp|lt|gt|quot|#39|nbsp|#160);/g, (_, e) => ENTITIES[e]);
  const attrs = [...html.matchAll(/\s(?:aria-label|title)="([^"]*)"/g)].map((m) => m[1]);
  const text = html.replace(/<(script|style)\b[\s\S]*?<\/\1>/gi, " ").replace(/<[^>]*>/g, " ");
  return decode([text, ...attrs].join(" "));
}

/**
 * The figures on one page that read the same in both builds, apart from the `explained` ones
 * (typed in the text, or allowed). Place by place when both pages show as many figures; otherwise
 * every figure of the first that the second shows too.
 */
export function sameOnPage(htmlA, htmlB, explained = new Set()) {
  const a = figuresIn(pageText(htmlA));
  const b = figuresIn(pageText(htmlB));
  const same =
    a.length === b.length ? a.filter((f, i) => f === b[i]) : a.filter((f) => b.includes(f));
  return same.filter((f) => !explained.has(f));
}

/** The HTML pages under a folder, relative to it, sorted. */
export function pages(dir) {
  const walk = (d) =>
    fs
      .readdirSync(d, { withFileTypes: true })
      .flatMap((e) =>
        e.isDirectory()
          ? walk(path.join(d, e.name))
          : e.name.endsWith(".html")
            ? [path.join(d, e.name)]
            : [],
      );
  return walk(dir)
    .map((f) => path.relative(dir, f))
    .sort();
}

/** Every page's figures that read the same in the two builds: [{ page, figures }], and the pages
 * only one build has. */
export function sameInBoth(dirA, dirB, explained = new Set()) {
  const a = pages(dirA);
  const b = new Set(pages(dirB));
  const found = [];
  for (const page of a.filter((p) => b.has(p))) {
    const read = (dir) => fs.readFileSync(path.join(dir, page), "utf-8");
    const figures = sameOnPage(read(dirA), read(dirB), explained);
    if (figures.length) found.push({ page, figures });
  }
  return {
    found,
    unmatched: [...a.filter((p) => !b.has(p)), ...[...b].filter((p) => !a.includes(p))],
  };
}
