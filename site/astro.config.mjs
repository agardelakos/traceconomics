// A static site: every page is plain HTML built ahead of time. No server, no visitor data.
import { defineConfig } from "astro/config";

export default defineConfig({
  output: "static",
  // Every page exists in Greek and English, under /el/ and /en/. The root page is our own: it
  // sends a visitor on by the browser's language, with plain links as a fallback.
  i18n: {
    locales: ["el", "en"],
    defaultLocale: "el",
    routing: { prefixDefaultLocale: true, redirectToDefaultLocale: false },
  },
  trailingSlash: "ignore",
  build: {
    // Styles and scripts as files, never inline, so a strict Content Security Policy can be set.
    inlineStylesheets: "never",
    format: "directory",
  },
  vite: {
    build: { assetsInlineLimit: 0 },
  },
});
