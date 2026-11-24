import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { lcovLines, mappings, ran, sorted } from "./code-map-read.mjs";

describe("the code map's readers", () => {
  it(
    "reads a source map's mappings as source and line",
    {
      meta: {
        id: "VT-CODEMAP-001",
        given: [
          "a source map's mappings with segments naming two sources, a segment naming none, and a line that steps back",
        ],
        when: "the mappings are read",
        then: [
          "each segment that names a source gives its source and line, counted from the values before it",
          "a segment that names no source is skipped",
          "a negative step moves the line back",
        ],
      },
    },
    () => {
      // "AACA": source +0, line +1; "EAAE": the same line; "G": a column only; "ACEA": source +1, line +2.
      expect([...mappings("AAAA;AACA,EAAE,G;ACEA")]).toEqual([
        [0, 0],
        [0, 1],
        [0, 1],
        [1, 3],
      ]);
      expect([...mappings("AAEA;AADA")]).toEqual([
        [0, 2],
        [0, 1],
      ]); // "D" is -1
    },
  );

  it(
    "reads an lcov file's lines and a codecov count, and sorts what it writes",
    {
      meta: {
        id: "VT-CODEMAP-002",
        given:
          "an lcov file of two files, with lines run and not run, and codecov counts of each kind",
        when: "its lines are read, all of them and those that ran, and the counts are read",
        then: [
          "all of them gives every line with code of each file",
          "those that ran leaves out the lines with no hits",
          "a count above 0 and branches with at least one taken count as run; 0 and no branch taken don't",
          "files and lines come out sorted",
        ],
      },
    },
    () => {
      const dir = mkdtempSync(join(tmpdir(), "code-map-"));
      const lcov = join(dir, "lcov.info");
      writeFileSync(
        lcov,
        "SF:src/b.ts\nDA:3,0\nDA:1,2\nend_of_record\nSF:src/a.ts\nDA:5,1\nend_of_record\n",
      );
      expect(lcovLines(lcov)).toEqual({ "src/a.ts": [5], "src/b.ts": [1, 3] });
      expect(lcovLines(lcov, { ranOnly: true })).toEqual({ "src/a.ts": [5], "src/b.ts": [1] });
      expect([1, 0, "1/2", "0/2"].map(ran)).toEqual([true, false, true, false]);
      expect(Object.keys(sorted({ b: [2, 1], a: [3] }))).toEqual(["a", "b"]);
      expect(sorted({ b: new Set([2, 1]) })).toEqual({ b: [1, 2] });
    },
  );
});
