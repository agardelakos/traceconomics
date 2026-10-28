# The TracEconomics website

Static pages built with [Astro](https://astro.build) and [Observable Plot](https://observablehq.com/plot/), in English (`/en/`) and Greek (`/el/`). The pages show pre-computed numbers only; the browser computes nothing but the personal calculator.

## What you need

- **Node.js 22 or later** (CI uses 24).
- **The data files** in `public/data/`. They are not in the repository: the pipeline writes them (from the repository root, `python -m traceconomics export site --out site/public/data`; see the root README). Without them the build stops.

Then, once, in this folder:

```sh
npm ci            # installs the exact versions in package-lock.json
```

## Looking at the site

Two ways, both on http://localhost:4321:

```sh
npm run dev       # while editing: rebuilds and reloads the page on every change
```

```sh
npm run build     # builds the site into dist/
npm run preview   # serves dist/ exactly as it will be published
```

`preview` serves the last build: after a change, build again. Stop either with Ctrl+C.

## Checks

```sh
npm run check     # type check, tests (incl. the calculator matching the published series), build, site checks
npm run a11y      # accessibility (axe) at phone and desktop width, light and dark; needs `npm run preview` running
npm run shots -- <out folder>   # screenshots of every page; needs `npm run preview` running
```

The security headers (`public/_headers`) apply only when the site is served as the host serves it:

```sh
npx wrangler dev --port 8788      # in one terminal: dist/ with the headers applied
npm run csp                       # in another: every page checked for Content Security Policy violations
```

`npm run check` fails on a missing translation, an unknown source, an inline script, a resource from another site, a broken internal link, or a page over its size budget.

## Where things are

| Folder | What it holds |
|---|---|
| `src/pages/` | One file per kind of page; addresses are `/{lang}/{country}/{topic}/…` |
| `src/content/` | The written text: glossary, method pages, other pages, the topic's steps, in `en/` and `el/` |
| `src/i18n/` | Interface text (`en.json`, `el.json`: the same keys in both) and which languages are offered |
| `src/lib/` | Build-time code: reading the data, formatting, the calculator engine, the topic list |
| `src/scripts/` | The little code that runs in the browser: charts, the explore page, the calculator |
| `scripts/` | The checks above |
| `public/` | Files served as they are, including `_headers` and, once written, `data/` |
