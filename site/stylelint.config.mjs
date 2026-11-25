// Stylelint: the recommended rules (likely mistakes only, like ESLint's; formatting is Prettier's
// job), then the site's own rules: spacing, control heights, font sizes, font weights and
// colours come only from src/styles/tokens.css, and the breakpoints are an agreed list. A value
// typed anywhere else drifts from the scale, which is how the site ended up with four control
// heights and six breakpoints. The reasons are in the wiki, "Site patterns". The CSS lives only in
// src/styles/ (site check 12 refuses <style> blocks in .astro files), so this sees all of it.

// One part of a spacing value: zero, auto, a space token, or arithmetic on tokens (no lengths
// typed in: `100vw` is the only unit, for centring a full-screen chart).
const ARITH = String.raw`(?:[-\d.\s*/+]|var\(--[a-z0-9-]+\)|100vw|\((?:[-\d.\s*/+]|var\(--[a-z0-9-]+\)|100vw)*\))+`;
const PART = String.raw`(?:0|auto|var\(--space-[a-z0-9]+\)|calc\(${ARITH}\)|max\((?:var\(--space-[a-z0-9]+\)|calc\(${ARITH}\))(?:,\s*(?:var\(--space-[a-z0-9]+\)|calc\(${ARITH}\)))*\))`;
const SPACING = new RegExp(String.raw`^${PART}(?:\s+${PART}){0,3}$`);

export default {
  extends: ["stylelint-config-recommended"],
  rules: {
    // Off: it flags unrelated selectors that only share an element type (a header link and a
    // breadcrumb link), and satisfying it means reordering global.css, which risks the cascade
    // for no fix.
    "no-descending-specificity": null,
    "declaration-property-value-allowed-list": {
      "/^(gap|row-gap|column-gap|margin|margin-[a-z-]+|padding|padding-[a-z-]+)$/": [SPACING],
      "font-size": [/^var\(--text-[a-z0-9-]+\)$/, "inherit"],
      "font-weight": [/^var\(--weight-[a-z]+\)$/, "inherit"],
    },
    // A control's height: 24-64px typed in is a control that skipped --control-h. Larger heights
    // (a chart's place) are layout, not controls.
    "declaration-property-value-disallowed-list": {
      "/^(min-)?height$/": [/^(2[4-9]|[3-5]\d|6[0-4])px$/],
    },
    "color-no-hex": true,
    "color-named": "never",
    "function-disallowed-list": ["rgb", "rgba", "hsl", "hsla"],
    // Media queries can't read custom properties, so the breakpoints are this list: a phone
    // below 600px, a wide screen from 900px. Written as ranges (`width < 600px`), so no 599/600
    // pairs.
    "media-feature-name-value-allowed-list": { width: ["600px", "900px"] },
    "media-feature-range-notation": "context",
  },
  overrides: [
    {
      // The tokens are where the values are typed.
      files: ["src/styles/tokens.css"],
      rules: {
        "color-no-hex": null,
        "function-disallowed-list": null,
        "declaration-property-value-allowed-list": null,
      },
    },
  ],
};
