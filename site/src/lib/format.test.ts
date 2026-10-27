import { describe, expect, it } from "vitest";
import { num } from "./format";

describe("num", () => {
  it("keeps each language's decimal mark", () => {
    expect(num("en", 5.14)).toBe("5.1");
    expect(num("el", 5.14)).toBe("5,1");
    expect(num("en", -0.04)).toBe("0.0");
  });

  it("splits thousands with a narrow space in both languages", () => {
    expect(num("en", 6123, 0)).toBe("6 123");
    expect(num("el", 6123, 0)).toBe("6 123");
    expect(num("el", 14931.25, 1)).toBe("14 931,3");
    expect(num("en", 999, 0)).toBe("999");
  });
});
