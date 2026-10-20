// The site's written content: glossary terms and method pages, one Markdown file each, per
// language (src/content/<collection>/<lang>/<slug>.md). Every entry names its sources by
// bibliography key; the pages check the keys exist.

import { defineCollection } from "astro:content";
import { glob } from "astro/loaders";
import { z } from "astro/zod";

const glossary = defineCollection({
  loader: glob({ pattern: "**/*.md", base: "./src/content/glossary" }),
  schema: z.object({
    term: z.string(),
    short: z.string(),                 // one plain sentence: the popover and the index
    other: z.string(),                 // the term in the other site language
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

export const collections = { glossary, method, pages };
