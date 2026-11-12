// The final-ν rule in the Greek text.
import { describe, expect, it } from "vitest";
import { finalN, keepsN } from "./final-n.mjs";

describe("the final ν", () => {
  it(
    "knows which sounds keep the ν",
    {
      meta: {
        id: "VT-FINALN-001",
        given:
          "words starting with a vowel, an accented vowel, κ π τ ξ ψ, μπ ντ γκ, and other consonants",
        when: "each is asked whether a ν stays before it",
        then: [
          "vowels (accented or capital too) and κ π τ ξ ψ μπ ντ γκ keep it",
          "θ, φ, σ, μ (not μπ), ν (not ντ), γ (not γκ) and λ drop it",
        ],
      },
    },
    () => {
      for (const w of [
        "άλλο",
        "Έτος",
        "κάνει",
        "πόλη",
        "τιμή",
        "ξένο",
        "ψωμί",
        "μπορεί",
        "ντομάτα",
        "γκρεμός",
        "ώρα",
      ])
        expect(keepsN(w), w).toBe(true);
      for (const w of ["θέλω", "φέρει", "σπίτι", "μέρα", "νόμο", "γάλα", "λέει"])
        expect(keepsN(w), w).toBe(false);
    },
  );

  it(
    "accepts the rule's own examples and finds the breaks of «δε(ν)» both ways",
    {
      meta: {
        id: "VT-FINALN-002",
        given: "«δεν κάνει τίποτα» and «δε θέλω», then «δεν θέλω» and «δε κάνει», one capitalised",
        when: "the text is checked",
        then: [
          "the first two pass",
          "«δεν θέλω» should be «δε θέλω» and «Δε κάνει» should be «Δεν κάνει», at their offsets",
        ],
      },
    },
    () => {
      expect(finalN("Δεν κάνει τίποτα. Δε θέλω.")).toEqual([]);
      const text = "Δεν θέλω. Και Δε κάνει.";
      expect(finalN(text)).toEqual([
        { at: 0, found: "Δεν θέλω", want: "Δε θέλω" },
        { at: text.indexOf("Δε κάνει"), found: "Δε κάνει", want: "Δεν κάνει" },
      ]);
    },
  );

  it(
    "checks the article «τη(ν)» and «στη(ν)» both ways",
    {
      meta: {
        id: "VT-FINALN-003",
        given:
          "«την πόλη», «τη μέρα», «στην αρχή», «στη Θεσσαλονίκη», then «την μέρα» and «στη αρχή»",
        when: "the text is checked",
        then: "only «την μέρα» (→ «τη μέρα») and «στη αρχή» (→ «στην αρχή») are found",
      },
    },
    () => {
      const ok = "την πόλη, τη μέρα, στην αρχή, στη Θεσσαλονίκη";
      expect(finalN(ok)).toEqual([]);
      expect(finalN("την μέρα και στη αρχή").map((f) => f.want)).toEqual(["τη μέρα", "στην αρχή"]);
    },
  );

  it(
    "judges «μη(ν)» and «αυτή(ν)» only where a ν is too many",
    {
      meta: {
        id: "VT-FINALN-004",
        given:
          "«μην φύγεις», «αυτήν τη φορά» before consonants that drop the ν, and «μη επιλέξιμος», «αυτή είναι» without one before vowels",
        when: "the text is checked",
        then: [
          "«μην φύγεις» → «μη φύγεις» is found",
          "«μη επιλέξιμος» and «αυτή είναι» pass: without ν they are right in other uses",
        ],
      },
    },
    () => {
      expect(finalN("Μην φύγεις.").map((f) => f.want)).toEqual(["Μη φύγεις"]);
      expect(finalN("Ένας μη επιλέξιμος τίτλος. Αυτή είναι η αρχή.")).toEqual([]);
    },
  );

  it(
    "leaves the contrast particle and words in other scripts alone",
    {
      meta: {
        id: "VT-FINALN-005",
        given: "«ο δε Γιάννης», «την Eurostat» and «την 1η»",
        when: "the text is checked",
        then: "nothing is found: «δε» after an article is the contrast particle, and only Greek words are judged",
      },
    },
    () => {
      expect(finalN("Η Μαρία κοιμάται, ο δε Γιάννης είναι έξω. Στην Eurostat, την 1η.")).toEqual(
        [],
      );
    },
  );
});
