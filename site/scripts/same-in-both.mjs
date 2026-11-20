// The site built on two made-up data sets: fails on a figure that reads the same in both
// (src/lib/same-in-both.mjs). Usage, from site/: node scripts/same-in-both.mjs <dist-a> <dist-b>
import fs from "node:fs";
import path from "node:path";
import { siteFigures } from "../src/lib/quoted-figures.mjs";
import { pages, sameInBoth } from "../src/lib/same-in-both.mjs";

const [a, b] = process.argv.slice(2);
if (!a || !b) {
  console.error("usage: node scripts/same-in-both.mjs <dist-a> <dist-b>");
  process.exit(2);
}
const src = path.resolve(import.meta.dirname, "..", "src");
// Typed in the text: listed and kinded by site check 11 already.
const typed = siteFigures(src).flatMap((f) => [...f.en, ...f.el]);
const allowed = JSON.parse(
  fs.readFileSync(path.join(src, "i18n", "same-in-both-allow.json"), "utf-8"),
).entries;
const { found, unmatched } = sameInBoth(a, b, new Set([...typed, ...allowed.map((e) => e.figure)]));
for (const { page, figures } of found) {
  console.error(`${page}: reads the same with other data: ${figures.join(", ")}`);
}
for (const page of unmatched) console.error(`${page}: built from one data set only`);
if (found.length || unmatched.length) {
  console.error(
    "A figure that doesn't change with the data was typed into a page or component: show it from the data, " +
      "or list it in src/i18n/same-in-both-allow.json with its reason.",
  );
  process.exit(1);
}
console.log(`Same in both: none, on the ${pages(a).length} pages built from each data set.`);
