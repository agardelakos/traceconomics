import { describe, expect, it } from "vitest";
import el from "../i18n/el.json";
import en from "../i18n/en.json";
import { has, href, isOffered, LANGS, OFFERED, otherLang, t } from "./i18n";

describe("t", () => {
  it("returns a text in each language, with its slots filled", { meta: {
    id: "VT-I18N-001",
    given: "the site's English and Greek texts",
    when: "texts are looked up, one with a value for its slot",
    then: [
      "the English site name is TracEconomics",
      "the English text reads with the slot's value filled in",
      "the Greek text contains the slot's value",
    ],
  } }, () => {
    expect(t("en", "site.name")).toBe("TracEconomics");
    expect(t("en", "nav.quick", { name: "Topics" })).toBe("Topics: quick list");
    expect(t("el", "nav.quick", { name: "Θέματα" })).toContain("Θέματα");
  });

  it("refuses a missing key, never falling back to the other language", { meta: {
    id: "VT-I18N-002",
    given: "a key that has no text",
    when: "it is looked up",
    then: [
      "the lookup throws a \"missing text\" error",
      "the key check is true for a key that exists in English",
      "the key check is false for the missing key in Greek",
    ],
  } }, () => {
    expect(() => t("en", "no.such.key")).toThrow(/missing text/);
    expect(has("en", "site.name")).toBe(true);
    expect(has("el", "no.such.key")).toBe(false);
  });

  it("refuses a missing slot value", { meta: {
    id: "VT-I18N-003",
    given: "a text with a {name} slot",
    when: "it is looked up without a value for the slot",
    then: "the lookup throws an error saying the text needs {name}",
  } }, () => {
    expect(() => t("en", "nav.quick")).toThrow(/needs \{name\}/);
  });
});

describe("the language files", () => {
  it("have the same keys", { meta: {
    id: "VT-I18N-004",
    given: "the Greek and English language files",
    when: "their keys are compared",
    then: "both files hold the same set of keys",
  } }, () => {
    expect(Object.keys(el).sort()).toEqual(Object.keys(en).sort());
  });
});

describe("languages", () => {
  it("offer only built languages, at least one", { meta: {
    id: "VT-I18N-005",
    given: "the built and the offered languages",
    when: "they are compared",
    then: [
      "at least one language is offered",
      "every offered language is a built one",
      "the offered check is true exactly for the offered languages",
    ],
  } }, () => {
    expect(OFFERED.length).toBeGreaterThan(0);
    for (const l of OFFERED) expect(LANGS).toContain(l);
    for (const l of LANGS) expect(isOffered(l)).toBe(OFFERED.includes(l));
  });

  it("switch to the other language", { meta: {
    id: "VT-I18N-006",
    given: "each of the two languages",
    when: "the other language is asked for",
    then: [
      "Greek gives English",
      "English gives Greek",
    ],
  } }, () => {
    expect(otherLang("el")).toBe("en");
    expect(otherLang("en")).toBe("el");
  });
});

describe("href", () => {
  it("puts a path under its language, with one slash at each end", { meta: {
    id: "VT-I18N-007",
    given: "paths with no slash, one slash or two slashes at their ends, and no path",
    when: "each is made into an address in a language",
    then: [
      "no path gives the language's home address (/en/)",
      "each path sits under its language with exactly one slash at each end",
    ],
  } }, () => {
    expect(href("en")).toBe("/en/");
    expect(href("el", "about")).toBe("/el/about/");
    expect(href("en", "/data/gr/")).toBe("/en/data/gr/");
    expect(href("en", "//glossary//")).toBe("/en/glossary/");
  });
});
