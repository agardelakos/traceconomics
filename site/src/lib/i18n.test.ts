import { describe, expect, it } from "vitest";
import el from "../i18n/el.json";
import en from "../i18n/en.json";
import { has, href, isOffered, LANGS, OFFERED, otherLang, t } from "./i18n";

describe("t", () => {
  it("returns a text in each language, with its slots filled", () => {
    expect(t("en", "site.name")).toBe("TracEconomics");
    expect(t("en", "nav.quick", { name: "Topics" })).toBe("Topics: quick list");
    expect(t("el", "nav.quick", { name: "Θέματα" })).toContain("Θέματα");
  });

  it("refuses a missing key, never falling back to the other language", () => {
    expect(() => t("en", "no.such.key")).toThrow(/missing text/);
    expect(has("en", "site.name")).toBe(true);
    expect(has("el", "no.such.key")).toBe(false);
  });

  it("refuses a missing slot value", () => {
    expect(() => t("en", "nav.quick")).toThrow(/needs \{name\}/);
  });
});

describe("the language files", () => {
  it("have the same keys", () => {
    expect(Object.keys(el).sort()).toEqual(Object.keys(en).sort());
  });
});

describe("languages", () => {
  it("offer only built languages, at least one", () => {
    expect(OFFERED.length).toBeGreaterThan(0);
    for (const l of OFFERED) expect(LANGS).toContain(l);
    for (const l of LANGS) expect(isOffered(l)).toBe(OFFERED.includes(l));
  });

  it("switch to the other language", () => {
    expect(otherLang("el")).toBe("en");
    expect(otherLang("en")).toBe("el");
  });
});

describe("href", () => {
  it("puts a path under its language, with one slash at each end", () => {
    expect(href("en")).toBe("/en/");
    expect(href("el", "about")).toBe("/el/about/");
    expect(href("en", "/data/gr/")).toBe("/en/data/gr/");
    expect(href("en", "//glossary//")).toBe("/en/glossary/");
  });
});
