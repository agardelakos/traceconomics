// The dark colours are written twice in tokens.css: once for the device setting, once for a
// reader who picked dark. CSS can't share one block between a media query and a selector, so
// this checks the two copies hold the same values.
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const css = readFileSync(new URL("./tokens.css", import.meta.url), "utf-8");

function declarations(block: string): string[] {
  return [...block.matchAll(/--[\w-]+:\s*[^;]+;/g)].map((m) => m[0].replace(/\s+/g, " "));
}

describe("dark theme tokens", () => {
  it("match between the device setting and the reader's choice", () => {
    const device = css.match(/:root:not\(\[data-theme="light"\]\) \{([^}]*)\}/);
    const chosen = css.match(/:root\[data-theme="dark"\] \{([^}]*--[^}]*)\}/);
    expect(device, "device-setting block").not.toBeNull();
    expect(chosen, "chosen-dark block").not.toBeNull();
    const a = declarations(device![1]);
    expect(a.length).toBeGreaterThan(10);
    expect(declarations(chosen![1])).toEqual(a);
  });
});
