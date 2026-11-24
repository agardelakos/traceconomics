// The code map's readers, without side effects, so they can be tested (code-map-read.test.ts):
// sorting, a codecov hit count, an lcov file, a source map's mappings. Used by code-map-lines.mjs.
import { readFileSync } from "node:fs";

/** {file: [line, …]} with files and lines sorted, so the same run gives the same bytes. */
export function sorted(byFile) {
  return Object.fromEntries(
    Object.keys(byFile)
      .sort()
      .map((f) => [f, [...byFile[f]].sort((a, b) => a - b)]),
  );
}

/** A codecov hit count that means "ran": a positive number, or branches "n/m" with n above 0. */
export const ran = (hits) => (typeof hits === "number" ? hits > 0 : !String(hits).startsWith("0/"));

/** Each file's lines with code, or only those that ran, from an lcov file ("SF:<file>", then "DA:<line>,<hits>"). */
export function lcovLines(path, { ranOnly = false } = {}) {
  const out = {};
  let current = null;
  for (const line of readFileSync(path, "utf-8").split("\n")) {
    if (line.startsWith("SF:")) out[(current = line.slice(3))] = [];
    else if (line.startsWith("DA:") && current) {
      const [n, hits] = line.slice(3).split(",").map(Number);
      if (!ranOnly || hits > 0) out[current].push(n);
    }
  }
  return sorted(out);
}

const BASE64 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

/** A source map's mappings as [source index, source line from 0], one per segment that names a source. */
export function* mappings(text) {
  let source = 0;
  let line = 0;
  for (const group of text.split(";"))
    for (const segment of group.split(",")) {
      if (!segment) continue;
      const values = [];
      let value = 0;
      let shift = 0;
      for (const ch of segment) {
        const digit = BASE64.indexOf(ch); // base64 VLQ: 5 bits a digit, the 6th says "more"
        value += (digit & 31) << shift;
        if (digit & 32) shift += 5;
        else {
          values.push(value & 1 ? -(value >> 1) : value >> 1);
          value = shift = 0;
        }
      }
      if (values.length >= 4) {
        source += values[1];
        line += values[2];
        yield [source, line];
      }
    }
}
