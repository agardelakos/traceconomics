import { describe, expect, it } from "vitest";
import { num } from "./format";

describe("num", () => {
  it(
    "keeps each language's decimal mark",
    {
      meta: {
        id: "VT-FMT-001",
        given: "numbers formatted with the default one decimal",
        when: "they are formatted in English and in Greek",
        then: [
          "English writes 5.14 as 5.1, with a decimal point",
          "Greek writes it as 5,1, with a decimal comma",
          "-0.04 is written 0.0, without a minus sign",
        ],
      },
    },
    () => {
      expect(num("en", 5.14)).toBe("5.1");
      expect(num("el", 5.14)).toBe("5,1");
      expect(num("en", -0.04)).toBe("0.0");
    },
  );

  it(
    "splits thousands with a narrow space in both languages",
    {
      meta: {
        id: "VT-FMT-002",
        given: "numbers of three to five whole digits",
        when: "they are formatted in English and in Greek",
        then: [
          "6123 is written 6 123 in both languages, split by a narrow space",
          "14931.25 to one decimal is written 14 931,3 in Greek",
          "999 is written without a separator",
        ],
      },
    },
    () => {
      expect(num("en", 6123, 0)).toBe("6 123");
      expect(num("el", 6123, 0)).toBe("6 123");
      expect(num("el", 14931.25, 1)).toBe("14 931,3");
      expect(num("en", 999, 0)).toBe("999");
    },
  );
});
