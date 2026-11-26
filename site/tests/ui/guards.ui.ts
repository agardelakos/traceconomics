// The harness tested: the site checks (scripts/checks.mjs) refuse what the hard rules forbid. Each
// test copies the built site and its sources, plants one violation in the copy, runs the checks there
// and expects them to fail naming it. A guard that has stopped working looks exactly like a clean
// site, so it is proved by breaking the rule on purpose. No browser: these run Node only, so they use
// Playwright's plain test (the shared fixtures in ./helpers open a page for every test).
import { execFileSync } from "node:child_process";
import {
  existsSync,
  linkSync,
  mkdirSync,
  readdirSync,
  readFileSync,
  rmSync,
  symlinkSync,
  unlinkSync,
  writeFileSync,
} from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test } from "@playwright/test";
import { gwt } from "./helpers";

const SITE = fileURLToPath(new URL("../..", import.meta.url));
const DIST = join(SITE, "dist");

// A copy of the site where every file is a hard link to the real one (instant, no space used), and
// its own scripts/, src/ and dist/ folders. Hard links share their bytes, so a planted file is always
// unlinked first and written new (`plant`): the real file is never touched.
function copy(from: string, to: string): void {
  mkdirSync(to, { recursive: true });
  for (const d of readdirSync(from, { withFileTypes: true })) {
    if (d.isDirectory()) copy(join(from, d.name), join(to, d.name));
    else if (d.isFile()) linkSync(join(from, d.name), join(to, d.name));
  }
}

// Each copy is removed when its test ends (a copy left in the project would be type-checked and
// linted as if it were source).
test.afterEach(() => rmSync(test.info().outputPath("site"), { recursive: true, force: true }));

function siteCopy(dir: string): string {
  for (const part of ["scripts", "src", "public", "dist"]) copy(join(SITE, part), join(dir, part));
  // The site's own settings files (astro.config.mjs, package.json, ...), read by some checks.
  for (const d of readdirSync(SITE, { withFileTypes: true }))
    if (d.isFile()) linkSync(join(SITE, d.name), join(dir, d.name));
  // Packages are only read: one link to the folder is enough.
  symlinkSync(join(SITE, "node_modules"), join(dir, "node_modules"));
  return dir;
}

function plant(path: string, change: (text: string) => string): void {
  const text = readFileSync(path, "utf-8");
  const changed = change(text);
  expect(changed, `nothing planted in ${path}`).not.toBe(text);
  unlinkSync(path);
  writeFileSync(path, changed);
}

// The checks' exit code and output, run in the copy.
function checks(dir: string): { failed: boolean; output: string } {
  try {
    return {
      failed: false,
      output: execFileSync("node", [join(dir, "scripts/checks.mjs")], { encoding: "utf-8" }),
    };
  } catch (e) {
    const err = e as { stdout?: string; stderr?: string };
    return { failed: true, output: `${err.stdout ?? ""}${err.stderr ?? ""}` };
  }
}

test.describe("guards", () => {
  test.skip(!existsSync(join(DIST, "en", "index.html")), "needs a build (dist/)");

  test(
    "the unchanged copy passes the site checks",
    gwt({
      id: "PW-GUARD-001",
      given: "a copy of the built site and its sources, nothing planted",
      when: "the site checks run on the copy",
      then: "they pass, so each failure below comes from what was planted",
    }),
    () => {
      const info = test.info();
      const result = checks(siteCopy(info.outputPath("site")));
      expect(result.output).toContain("All site checks passed.");
      expect(result.failed).toBe(false);
    },
  );

  test(
    "an English text without its Greek twin fails the site checks",
    gwt({
      id: "PW-GUARD-002",
      given: "a copy of the site whose English interface text gained a key the Greek lacks",
      when: "the site checks run on the copy",
      then: "they fail, naming the key as English only",
    }),
    () => {
      const info = test.info();
      const dir = siteCopy(info.outputPath("site"));
      plant(join(dir, "src/i18n/en.json"), (t) =>
        t.replace(/^\{/, '{\n  "planted.english-only": "Only in English",'),
      );
      const result = checks(dir);
      expect(result.failed).toBe(true);
      expect(result.output).toContain("text key only in English: planted.english-only");
    },
  );

  test(
    "an inline script or another site's script in a page fails the site checks",
    gwt({
      id: "PW-GUARD-003",
      given:
        "a copy of the built site whose English home page gained an inline script and a script from another site",
      when: "the site checks run on the copy",
      then: "they fail, naming the page for each",
    }),
    () => {
      const info = test.info();
      const dir = siteCopy(info.outputPath("site"));
      plant(join(dir, "dist/en/index.html"), (t) =>
        t.replace(
          "</body>",
          '<script>alert(1)</script><script src="https://cdn.example.org/x.js"></script></body>',
        ),
      );
      const result = checks(dir);
      expect(result.failed).toBe(true);
      expect(result.output).toMatch(/en[\\/]index\.html: inline script/);
      expect(result.output).toMatch(
        /en[\\/]index\.html: script from https:\/\/cdn\.example\.org\/x\.js/,
      );
    },
  );
});
