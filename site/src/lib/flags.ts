// Each covered country's flag, drawn here as a small SVG (3:2), so every system shows the same
// picture: emoji flags show as two letters on Windows. A flag sits next to the country's name and
// never replaces it, so it is hidden from screen readers. A country gets its flag when it gets
// its pages; one without a flag stops the build.

const FLAGS: Record<string, string> = {
  // Greece: nine blue and white stripes, a white cross on blue in the corner (5 stripes square).
  gr: '<rect width="27" height="18" fill="#0D5EAF"/><path d="M10 3h17M10 7h17M0 11h27M0 15h27M5 0v10M0 5h10" stroke="#fff" stroke-width="2"/>',
};

export function flag(country: string): string {
  const shape = FLAGS[country];
  if (!shape) throw new Error(`no flag for "${country}": add it to src/lib/flags.ts`);
  return `<svg class="country-flag" width="21" height="14" viewBox="0 0 27 18" aria-hidden="true">${shape}</svg>`;
}
