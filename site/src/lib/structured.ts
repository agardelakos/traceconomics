// Descriptions for search engines and other tools that read pages (schema.org, as JSON-LD): a
// dataset's name, licence, period, place and files, so a search for data can find the files and
// a program can fetch them without reading the page. Only facts the published files state, and no
// build time (`generated_at`): every build of the same data must give the same pages.

/** The licences our files may carry (metadata.json `licence`), by their canonical address. */
const LICENCES: Record<string, string> = { "CC BY 4.0": "https://creativecommons.org/licenses/by/4.0/" };

const FORMATS: Record<string, string> = {
  ".csv": "text/csv",
  ".parquet": "application/vnd.apache.parquet",
  ".json": "application/json",
};

export interface DatasetInput {
  site: URL;                       // the public address (Astro.site)
  lang: string;
  name: string;
  description: string;
  page: string;                    // the dataset's place on its page, from the site's root ("/en/data/gr/#…")
  metadata: { licence: string; first_period: string; last_period: string; attribution: string };
  place: string;                   // the country's name
  basedOn: string[];               // the publishers' home pages
  files: string[];                 // addresses from the site's root ("/data/v1/…")
}

export function dataset(d: DatasetInput): Record<string, unknown> {
  const licence = LICENCES[d.metadata.licence];
  if (!licence) throw new Error(`unknown licence "${d.metadata.licence}": add its address to LICENCES`);
  const full = (p: string) => new URL(p, d.site).href;
  return {
    "@context": "https://schema.org",
    "@type": "Dataset",
    name: d.name,
    description: d.description,
    url: full(d.page),
    inLanguage: d.lang,
    license: licence,
    isAccessibleForFree: true,
    creator: { "@type": "Organization", name: "TracEconomics", url: full("/") },
    creditText: d.metadata.attribution,
    temporalCoverage: `${d.metadata.first_period}/${d.metadata.last_period}`,
    spatialCoverage: { "@type": "Place", name: d.place },
    isBasedOn: d.basedOn,
    distribution: d.files.map((f) => {
      const format = FORMATS[f.slice(f.lastIndexOf("."))];
      if (!format) throw new Error(`no media type for ${f}`);
      return { "@type": "DataDownload", contentUrl: full(f), encodingFormat: format };
    }),
  };
}

/**
 * JSON for a <script type="application/ld+json"> block. "<" is written as < so no text in it
 * can close the element ("</script>") or open a comment; JSON readers see the same characters.
 */
export function ldJson(value: unknown): string {
  return JSON.stringify(value).replace(/</g, "\\u003c");
}
