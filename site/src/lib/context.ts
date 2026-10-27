// The figures a country's card shows on the home page: the official inflation rate as the statistics
// office published it, and as we compute it from the office's own index levels. Each keeps its own
// month: if one lags, the card says so rather than hide it. Where the two share a month, the card
// says whether they agree; a disagreement is shown, never hidden (`official.json`).

import { m1Dir, readJson } from "./data";

export interface Rate { source: string; reference: string; period: string; annual_rate: number; annual_rate_full: number }
export interface Official {
  computed: Rate;
  published: Rate;
  comparison?: { period: string; difference: number; agree: boolean };
}

export function countryFacts(country: string) {
  return { official: readJson<Official>(`${m1Dir(country)}/official.json`) };
}
