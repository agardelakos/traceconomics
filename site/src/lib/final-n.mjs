// The final ν in Greek: «δεν», «μην», «την», «στην», «αυτήν» keep it before a vowel or before κ,
// π, τ, ξ, ψ, μπ, ντ, γκ (consonants that would otherwise merge with it), and drop it before any
// other consonant: «δεν κάνει», «δε θέλω», «την πόλη», «τη μέρα». The rule follows the sound of
// the next word, so only a next word in Greek letters is judged (a Latin name or a number is
// not: "Eurostat" starts with a /j/ sound).
//
// Which words are judged in which direction:
// - «δε(ν)», «τη(ν)», «στη(ν)»: both ways. «τη» and «στη» are only ever the accusative article;
//   «δε» after an article is the contrast particle («ο δε Γιάννης»), which never takes ν, so it
//   is left alone there.
// - «μη(ν)», «αυτή(ν)»: only a ν before a consonant that drops it. Without ν they are also right
//   in other uses a rule can't tell apart: «μη» before an adjective («μη επιλέξιμος»), «αυτή» as
//   the nominative («αυτή είναι»).
// Plain JavaScript, like twin-terms.mjs, so the site checks can load it without a build.

const KEEPS = /^(?:[αεηιουωκπτξψ]|μπ|ντ|γκ)/;
const BOTH = new Set(["δε", "δεν", "τη", "την", "στη", "στην"]);
const DROP_ONLY = new Set(["μην", "αυτήν"]);
const ARTICLES = new Set(["ο", "η", "το", "οι", "τα", "του", "της", "των", "τους", "τις"]);
const GREEK = /^[Ͱ-Ͽἀ-῿]/;

// Accents and diaeresis off, lower case: «Έτος» starts with ε.
const bare = (s) => s.normalize("NFD").replace(/\p{M}/gu, "").normalize("NFC").toLowerCase();

/** Whether a word keeps a ν before it. */
export function keepsN(word) {
  return KEEPS.test(bare(word).slice(0, 2));
}

/**
 * The places in a Greek text that break the rule: [{ at, found, want }], `found` being the
 * particle and the next word as written, `want` the particle as it should be.
 */
export function finalN(text) {
  const out = [];
  const re = /(?<![\p{L}\p{N}])(?:(\p{L}+)\s+)?(δεν|δε|την|τη|στην|στη|μην|αυτήν)\s+(\p{L}+)/giu;
  for (const m of text.matchAll(re)) {
    const [, before, particle, next] = m;
    const p = particle.toLowerCase();
    if (!GREEK.test(next)) continue;
    if ((p === "δε" || p === "δεν") && before && ARTICLES.has(before.toLowerCase())) continue;
    const keep = keepsN(next);
    const hasN = p.endsWith("ν");
    let want = null;
    if (hasN && !keep && (BOTH.has(p) || DROP_ONLY.has(p))) want = particle.slice(0, -1);
    else if (!hasN && keep && BOTH.has(p)) want = `${particle}ν`;
    if (want) {
      // The particle's offset: after the optional word before it and its spaces.
      const at = m.index + (before ? m[0].indexOf(particle, before.length) : 0);
      out.push({ at, found: `${particle} ${next}`, want: `${want} ${next}` });
    }
  }
  return out;
}
