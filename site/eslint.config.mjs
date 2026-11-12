// Likely bugs in the site's code, not style (style is Prettier's): the three recommended sets only.
// Add rules one at a time, each in its own change. An exception names its reason:
// `// eslint-disable-next-line <rule> -- <reason>`.
import js from "@eslint/js";
import astro from "eslint-plugin-astro";
import tseslint from "typescript-eslint";

export default [
  {
    // Generated or served as written; never linted.
    ignores: ["dist/", "coverage/", "public/", ".astro/", "test-results/", "playwright-report/"],
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  ...astro.configs.recommended,
  {
    // The .mjs files are Node scripts (build, checks, reports); ESLint can't tell. The Node globals
    // they use, named here rather than through another dependency. Add one when a script needs it.
    files: ["**/*.mjs"],
    languageOptions: { globals: { console: "readonly", process: "readonly", URL: "readonly" } },
  },
  {
    // `const { dropped: _, ...rest } = obj` is how a key is left out of a copy; the rest is used.
    rules: { "@typescript-eslint/no-unused-vars": ["error", { ignoreRestSiblings: true }] },
  },
  {
    // An exception that no longer silences anything is reported, so stale ones don't pile up.
    linterOptions: { reportUnusedDisableDirectives: "error" },
  },
];
