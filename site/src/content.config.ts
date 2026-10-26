// The site's written content: glossary terms and method pages, one Markdown file each, per
// language (src/content/<collection>/<lang>/<slug>.md). Every entry names its sources by
// bibliography key; the pages check the keys exist.

import { defineCollection } from "astro:content";
import { glob } from "astro/loaders";
import { z } from "astro/zod";
import { GLOSSARY_CATEGORIES } from "./lib/glossary";

const glossary = defineCollection({
  loader: glob({ pattern: "**/*.md", base: "./src/content/glossary" }),
  schema: z.object({
    term: z.string(),
    // The words that mark this term in running text, in every form it takes (Greek inflects):
    // the first mention on each page becomes a popover (src/lib/glossary-terms.mjs).
    forms: z.array(z.string()).min(1),
    short: z.string(),                 // one plain sentence: the popover and the index
    other: z.string(),                 // the term in the other site language
    category: z.enum(GLOSSARY_CATEGORIES),  // where the glossary's index lists it (lib/glossary.ts)
    sources: z.array(z.string()).min(1),
    related: z.array(z.string()).default([]),
  }),
});

const method = defineCollection({
  loader: glob({ pattern: "**/*.md", base: "./src/content/method" }),
  schema: z.object({
    title: z.string(),
    summary: z.string(),
    order: z.number(),
    option: z.string().optional(),     // the option key this page explains, if any
    sources: z.array(z.string()).min(1),
  }),
});

const pages = defineCollection({
  loader: glob({ pattern: "**/*.md", base: "./src/content/pages" }),
  schema: z.object({
    title: z.string(),
    summary: z.string(),
    sources: z.array(z.string()).default([]),
  }),
});

// A topic's explainer for the curious non-expert, one short step per file, shown as cards in order
// on the topic's page (src/content/steps/<lang>/<topic module>-<n>.md). Nothing country-specific.
const steps = defineCollection({
  loader: glob({ pattern: "**/*.md", base: "./src/content/steps" }),
  schema: z.object({
    title: z.string(),
    order: z.number(),
    sources: z.array(z.string()).default([]),
  }),
});

export const collections = { glossary, method, pages, steps };
