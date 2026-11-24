// The front end's part of the wiki's code map: which test runs which lines of the site's own code,
// reduced from each suite's raw coverage to small JSON files in coverage/code-map/, which
// tests/coverage/code_map.py reads. Run in a coverage build (TRACECONOMICS_COVERAGE=on).
//
//   node scripts/code-map-lines.mjs lines        every line with code, from the merged report
//                                                (coverage/report/lcov.info, scripts/coverage.mjs),
//                                                and the lines each layer's merged run ran
//                                                (coverage/layers/<layer>/lcov.info), as the badge counts;
//                                                and the lines the build put in the browser's scripts
//                                                (from dist/_astro/*.map)
//   node scripts/code-map-lines.mjs vitest       runs each Vitest file alone with coverage, then its
//                                                lines; the layer from VITEST_INTEGRATION
//   node scripts/code-map-lines.mjs playwright   each case's lines, from the folders the browser
//                                                tests write with TRACECONOMICS_CODE_MAP=on
//   node scripts/code-map-lines.mjs selenium DIR each Selenium test's lines, from the entries
//                                                tests/selenium/page_coverage.py writes into DIR
//
// Lines are counted as the merged report counts them: the same converter (monocart), the same
// files (sourceFilter), the same names (sourcePath). A line counts as run when it ran at least once.
// How tests/coverage/code_map.py uses them (each line's status from the badge's merged runs,
// layers.json; which tests run it from each test's own lines, kept to layers.json for Vitest and to
// bundled.json for the browser suites) and why is in its docstring.
import { spawnSync } from "node:child_process";
import { existsSync, mkdirSync, readdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { basename, join, relative } from "node:path";
import { CoverageReport } from "monocart-coverage-reports";
import { lcovLines, mappings, ran, sorted } from "./code-map-read.mjs";
import {
  CODE_MAP_DIR,
  VITEST_INTEGRATION,
  sourceFilter,
  sourcePath,
  ui,
} from "./coverage-options.mjs";

const OUT = "coverage/code-map";
const TMP = "coverage/code-map-tmp";

/** The covered lines of raw coverage (a folder of monocart's raw data, or V8 entries). */
async function covered(name, { inputDir, entries }) {
  rmSync(TMP, { recursive: true, force: true });
  if (entries) {
    await new CoverageReport({ ...ui, outputDir: `${TMP}/in` }).add(entries);
    inputDir = `${TMP}/in/.cache`;
  }
  await new CoverageReport({
    name,
    inputDir,
    outputDir: `${TMP}/out`,
    reports: ["codecov"],
    logging: "error",
    sourceFilter,
    sourcePath,
  }).generate();
  const cc = JSON.parse(readFileSync(`${TMP}/out/codecov.json`, "utf-8")).coverage;
  rmSync(TMP, { recursive: true, force: true });
  const out = {};
  for (const [f, lines] of Object.entries(cc)) {
    const hit = Object.entries(lines)
      .filter(([, h]) => ran(h))
      .map(([l]) => Number(l));
    if (hit.length) out[f] = hit;
  }
  return out;
}

/** {file: [line, …]}: the source lines that have code in the built scripts (dist/_astro). */
function bundledLines(dir = "dist/_astro") {
  const out = {};
  for (const f of readdirSync(dir)
    .filter((f) => f.endsWith(".js.map"))
    .sort()) {
    const map = JSON.parse(readFileSync(join(dir, f), "utf-8"));
    for (const [s, l] of mappings(map.mappings)) {
      const name = map.sources[s];
      if (sourceFilter(name)) (out[sourcePath(name)] ??= new Set()).add(l + 1);
    }
  }
  return sorted(out);
}

/** The Vitest files, as the repository names them. */
function vitestFiles(dir = "src") {
  return readdirSync(dir, { withFileTypes: true })
    .flatMap((e) => {
      const p = join(dir, e.name);
      if (e.isDirectory()) return vitestFiles(p);
      return e.name.endsWith(".test.ts") ? [relative(".", p).replaceAll("\\", "/")] : [];
    })
    .sort();
}

function write(name, data) {
  mkdirSync(OUT, { recursive: true });
  writeFileSync(`${OUT}/${name}.json`, JSON.stringify(data) + "\n");
  console.log(`${OUT}/${name}.json: ${Object.keys(data).length} entries`);
}

const [what, arg] = process.argv.slice(2);

if (what === "lines") {
  write("lines", lcovLines("coverage/report/lcov.info"));
  const layers = {};
  for (const layer of ["unit", "integration", "e2e"])
    layers[layer] = lcovLines(`coverage/layers/${layer}/lcov.info`, { ranOnly: true });
  write("layers", layers);
  write("bundled", bundledLines());
} else if (what === "vitest") {
  const out = {};
  for (const [i, file] of vitestFiles().entries()) {
    const dir = `coverage/vitest-file/${i}`;
    const done = spawnSync(
      "npx",
      ["vitest", "run", file, `--outputFile.json=${dir}/results.json`],
      {
        stdio: ["ignore", "ignore", "inherit"],
        env: { ...process.env, TRACECONOMICS_COVERAGE: "on", TRACECONOMICS_COVERAGE_DIR: dir },
      },
    );
    if (done.status !== 0) {
      console.error(`${file}: Vitest failed on its own (exit ${done.status})`);
      process.exit(1);
    }
    out[file] = {
      layer: VITEST_INTEGRATION.includes(file) ? "integration" : "unit",
      lines: sorted(await covered(file, { inputDir: `${dir}/raw` })),
    };
    rmSync(dir, { recursive: true, force: true });
  }
  write("vitest", out);
} else if (what === "playwright") {
  const out = {};
  for (const test of existsSync(CODE_MAP_DIR) ? readdirSync(CODE_MAP_DIR).sort() : []) {
    const dir = `${CODE_MAP_DIR}/${test}`;
    const { id, title } = JSON.parse(readFileSync(`${dir}/case.json`, "utf-8"));
    const key = id ?? title; // every test carries a case; one without would be listed by its title
    const lines = await covered(test, { inputDir: `${dir}/.cache` });
    const into = (out[key] ??= {});
    for (const [f, ls] of Object.entries(lines))
      into[f] = [...new Set([...(into[f] ?? []), ...ls])];
  }
  for (const k of Object.keys(out)) out[k] = sorted(out[k]);
  write(
    "playwright",
    Object.fromEntries(
      Object.keys(out)
        .sort()
        .map((k) => [k, out[k]]),
    ),
  );
} else if (what === "selenium" && arg) {
  // Sources are written once per Chrome (they repeat in every test); each script's source map comes
  // from the build, since the test server is gone by now.
  const sources = {};
  for (const f of readdirSync(arg).filter((f) => f.startsWith("sources-")))
    Object.assign(sources, JSON.parse(readFileSync(join(arg, f), "utf-8")));
  const out = {};
  for (const f of readdirSync(arg)
    .filter((f) => f.startsWith("test-"))
    .sort()) {
    const { node, entries } = JSON.parse(readFileSync(join(arg, f), "utf-8"));
    const full = entries
      .filter((e) => sources[e.url] !== undefined)
      .map((e) => {
        const map = join("dist/_astro", basename(new URL(e.url).pathname) + ".map");
        return {
          ...e,
          source: sources[e.url],
          ...(existsSync(map) ? { sourceMap: JSON.parse(readFileSync(map, "utf-8")) } : {}),
        };
      });
    if (!full.length) continue;
    const lines = await covered(node, { entries: full });
    const into = (out[node] ??= {});
    for (const [file, ls] of Object.entries(lines))
      into[file] = [...new Set([...(into[file] ?? []), ...ls])];
  }
  for (const k of Object.keys(out)) out[k] = sorted(out[k]);
  write(
    "selenium",
    Object.fromEntries(
      Object.keys(out)
        .sort()
        .map((k) => [k, out[k]]),
    ),
  );
} else {
  console.error("usage: node scripts/code-map-lines.mjs lines|vitest|playwright|selenium DIR");
  process.exit(2);
}
