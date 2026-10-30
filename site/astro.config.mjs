// A static site: every page is plain HTML built ahead of time. No server, no visitor data.
import { satteri } from "@astrojs/markdown-satteri";
import { defineConfig } from "astro/config";
import { glossaryTerms } from "./src/lib/glossary-terms.mjs";
import { sitemap } from "./src/lib/sitemap.mjs";

export default defineConfig({
  output: "static",
  // The public address. Pages use it only where a full address is required: the sharing image,
  // the links for search engines (canonical, hreflang, the sitemap) and the dataset descriptions.
  site: "https://traceconomics.com",
  integrations: [sitemap()],
  // Every page exists in Greek and English, under /el/ and /en/. The root page is our own: it
  // sends a visitor on by the browser's language, with plain links as a fallback.
  i18n: {
    locales: ["el", "en"],
    defaultLocale: "el",
    routing: { prefixDefaultLocale: true, redirectToDefaultLocale: false },
  },
  trailingSlash: "ignore",
  // Glossary terms in the written pages open their explanation, as GlossaryTerm does in templates.
  markdown: { processor: satteri({ hastPlugins: [glossaryTerms()] }) },
  build: {
    // Styles and scripts as files, never inline, so a strict Content Security Policy can be set.
    inlineStylesheets: "never",
    format: "directory",
  },
  vite: {
    build: { assetsInlineLimit: 0 },
  },
});
