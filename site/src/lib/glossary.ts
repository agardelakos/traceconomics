// The glossary's categories, in reading order: from the basics to the technical. They group ideas,
// not topics, so a term like "percentage point" serves every topic from one place. Every term
// names exactly one (its file's `category`); the content schema refuses any other value.
export const GLOSSARY_CATEGORIES = ["prices", "households", "weights", "surveys"] as const;
export type GlossaryCategory = (typeof GLOSSARY_CATEGORIES)[number];
