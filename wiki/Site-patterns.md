# Site patterns

How the site's pages are put together: the navigation, the components, the values everything is
sized with, and the rules that keep them consistent. Each pattern says what it is for, when to use
it, when not to, and what it does for accessibility. The rules are checked automatically (last
section), so a page that skips a pattern fails the build rather than drifting from the rest.

Why it is done this way: a UI rule that lives only in someone's memory is missed by the next
contributor. So each rule is, in order of preference, **built into the structure** (a page gets it
without doing anything), **checked** (the build fails without it), or **written down** (here).

## Navigation: four levels

| Level        | Where                                                                                                                   | Built by                                                        |
| ------------ | ----------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------- |
| Header       | every page: Home, Topics and Countries (each with a quick list), Glossary, Data, About                                  | `site/src/components/SiteHeader.astro`                          |
| The bar      | a country's pages: the country, then a tab for each of its topics; a topic's page across countries: one tab per country | `CountryBar.astro`, `TopicBar.astro`                            |
| Section tabs | a topic's pages for one country: its sections (Overview, Method, …)                                                     | `CountryBar.astro`, from `sections` in `site/src/lib/topics.ts` |
| The strip    | a page inside a section (a method option, a check, a question): every page of that section                              | `CountryBar.astro`, from `site/src/lib/strips.ts`               |

**The strip is never passed in by a page.** A section with pages of its own is declared in
`topics.ts` (`inner`), and `strips.ts` lists its rows; the layout builds the strip from the page's
address. A new check, question or option gets its strip without anyone remembering it. A page
inside a section that isn't declared stops the build with a message naming the section.

**How the current item is marked.** `aria-current="page"` on the item that _is_ this page;
`aria-current="true"` on an item this page sits inside (the topic tab and the section tab on a
check's page). In the strip the current page is plain text, not a link to itself. Screen readers
announce both kinds; the styles show both.

**Short names, plain words.** Tabs and strips use short names; the page's title says the rest.

**Phones.** Every row scrolls sideways when it is wider than the screen, and opens scrolled so its
current item is in view (`site/src/scripts/topic-bar.ts`). It centres again once the site's fonts
have loaded, unless the reader has already moved the row.

**Planned topics and countries** are never named, except a planned topic marked `shown` in
`topics.ts`, as a greyed "Coming soon" card; one small card says more are planned
(`MoreCard.astro`).

## Components

The kit is small on purpose: a component exists where pages kept writing the same markup.
Everything else is a class pattern (below).

### Breadcrumb

`site/src/components/ui/Breadcrumb.astro`: Home, then each level up to the page itself (not a
link).

- **Use** on pages outside a country: the topic and country lists, the data pages, the glossary,
  About.
- **Don't** on a country's pages: the bar already says where the reader is.
- **Accessibility:** a `<nav>` named "Breadcrumb" in the reader's language.

### JumpLinks

`site/src/components/ui/JumpLinks.astro`: links to the parts of a long page ("On this page"),
as chips under its title.

- **Use** when a page has three or more parts a reader may want to jump to.
- **Don't** for links to other pages: use cards (CardNav) or the bar.
- **Accessibility:** a `<nav>` with its own name (`label`); each part it links to needs an `id`.

### CardNav

`site/src/components/ui/CardNav.astro`: a heading and a set of cards that lead to other pages
(the countries with a topic, the method's options).

- **Use** for a list of destinations that each need a sentence of explanation.
- **Don't** for actions (use buttons) or for parts of the same page (JumpLinks).
- **Accessibility:** a `<nav>` named by its own heading (`aria-labelledby`).

## Class patterns

Uniform already, so they stay classes, defined in `site/src/styles/global.css`:

- **Buttons:** `class="button"`, `class="button primary"` for the one main action in a group.
- **Cards:** `class="card"` (a link), inside `.cards` or `.card-row`.
- **Disclosures:** `<details class="panel">` with a `<summary>`; `.fold` inside a chart's panel.
- **A labelled control:** `<label class="stack field">`, `field-narrow` for a select.
- **Chips:** `.chip`, pressed with `aria-pressed="true"`; its thicker border is drawn inside, so it
  keeps its size.

## Values: the tokens

Every size, space, colour and weight comes from `site/src/styles/tokens.css`:

- **Spacing:** `--space-1` to `--space-8` (4, 8, 12, 16, 24, 32, 48, 64 px), and `--space-half`
  (2px) only inside small components (chips, flags, badges) and between rows that belong together.
- **Controls:** `--control-h` (44px) for buttons, tabs, chips and inputs; `--control-h-compact`
  (32px) for controls inside menus and folds. 44px meets WCAG 2.2's enhanced target size (2.5.5);
  32px meets the minimum (2.5.8, 24px) with room.
- **Type:** `--text-xs` to `--text-3xl` (12 to 36px), display sizes `--text-stat`, `--text-hero`,
  `--text-title` (the home page's title, which grows with the screen), and `--text-code` for code
  inside text. Weights `--weight-regular`, `--weight-semibold`, `--weight-bold`: the three the site
  loads.
- **Colours:** only the `--color-*` and `--series-*` tokens, each with its dark-mode value.
- **Breakpoints:** a phone below 600px, a wide screen from 900px; written as ranges,
  `@media (width < 600px)`, `@media (width >= 900px)`. CSS can't read a custom property in a media
  query, so these two numbers are the agreed list instead of tokens.

## Layout on a page: utilities, not inline styles

A page never writes `style="…"`. A one-element layout choice is a utility class from
`site/src/styles/utilities.css`, built from the tokens: `stack` with `gap-0` … `gap-8` or
`gap-half`, `mt-0` … `mt-8`, `m-0`, `measure` (a readable line length), `self-start`, `text-lg`,
`weight-semibold`, `font-sans`, `no-underline`. A choice used once that isn't a utility gets a
named class at the end of `global.css` ("Page pieces"). Add a utility only when a value repeats.

The one thing a `style` attribute may do is set **custom properties**, for values that come from
the data or name something: a bar's width and colour (``style={`--w: ${share}%; --c: ${colour}`}``),
a popover's anchor (`style="--anchor: --topic-menu"`). The CSS reads them. Scripts that draw
charts set their own sizes and colours; that is data, not layout.

## The rules, and where each is checked

| Rule                                                                                                                   | Checked by                                                                     |
| ---------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------ |
| Spacing, control heights, font sizes and weights from tokens; no typed colours; only the agreed breakpoints, as ranges | Stylelint (`site/stylelint.config.mjs`), in `npm run lint` and CI's `lint` job |
| A `style` attribute sets custom properties only                                                                        | site check 12 (`site/src/lib/ui-rules.mjs`)                                    |
| No `<style>` blocks in `.astro` files: all CSS in `site/src/styles/`, where Stylelint sees it                          | site check 12                                                                  |
| No `<nav>` in a page: navigation comes from components                                                                 | site check 12                                                                  |
| The breadcrumb only from its component                                                                                 | site check 12                                                                  |
| Every page inside a section shows the strip once, with one item marked                                                 | the build (`strips.ts`), then site check 13 on the built pages                 |
| A section with inner pages is declared, and has a row                                                                  | the build; Vitest (`site/src/lib/strips.test.ts`)                              |

Each rule is shown failing on a bad example and passing on a good one in Vitest
(`site/src/styles/stylelint.test.ts`, `site/src/lib/ui-rules.test.ts`). A line that has to break a
Stylelint rule says why on that line:
`/* stylelint-disable-next-line declaration-property-value-allowed-list -- a hairline: … */`.

Layout and navigation changes need a maintainer's agreement first (CONTRIBUTING.md).
