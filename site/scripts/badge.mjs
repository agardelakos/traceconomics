// The README's coverage badge: a small SVG with the figure from coverage/summary.json (written by
// scripts/coverage.mjs). Drawn here, not by a badge service, so no third party sees or serves it.
// Usage: node scripts/badge.mjs <out.svg>
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname } from "node:path";
import { FLOOR, GOOD, standing } from "./coverage-options.mjs";

const out = process.argv[2];
if (!out) {
  console.error("usage: node scripts/badge.mjs <out.svg>");
  process.exit(2);
}
const { pct } = JSON.parse(readFileSync("coverage/summary.json", "utf-8")).lines;

const label = "site coverage";
const value = `${pct}%`;
// Green from GOOD up, yellow from FLOOR, red below (the build fails there, so a red badge should
// never be published). Yellow takes dark text: white on yellow is hard to read.
const COLOURS = { good: ["#2e7d32", "#fff"], fair: ["#f2c94c", "#1a1a1a"], low: ["#c62828", "#fff"] };
const [color, ink] = COLOURS[standing(pct)];
// Width from the text: about 6.5 px a character at 11 px Verdana, plus padding.
const w = (s) => Math.round(s.length * 6.5) + 12;
const lw = w(label), vw = w(value), total = lw + vw;

const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${total}" height="20" role="img" aria-label="${label}: ${value}">
<title>${label}: ${value}</title>
<rect width="${lw}" height="20" fill="#555"/>
<rect x="${lw}" width="${vw}" height="20" fill="${color}"/>
<g text-anchor="middle" font-family="Verdana,DejaVu Sans,sans-serif" font-size="11">
<text x="${lw / 2}" y="14" fill="#fff">${label}</text>
<text x="${lw + vw / 2}" y="14" fill="${ink}">${value}</text>
</g>
</svg>
`;
mkdirSync(dirname(out), { recursive: true });
writeFileSync(out, svg);
console.log(`${out}: ${label} ${value} (${standing(pct)}: floor ${FLOOR}%, good from ${GOOD}%)`);
