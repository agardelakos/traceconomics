// Rounding that matches the published files to the last digit.
//
// The published numbers are rounded by Python (`round(x, 2)`, `f"{x:.1f}"`): to the nearest
// decimal of the double's exact value, and an exact halfway case goes to the even digit.
// JavaScript's toFixed sends halfway cases up, so it would disagree on values such as 100.125.
// Here the double's exact decimal expansion (toFixed(60) is exact for these magnitudes) is
// rounded by hand, half to even.

export function roundHalfEven(x: number, digits: number): number {
  if (!Number.isFinite(x)) return x;
  const negative = x < 0;
  const exact = Math.abs(x).toFixed(60);
  const [whole, frac] = exact.split(".");
  const kept = whole + frac.slice(0, digits);
  const rest = frac.slice(digits);
  let n = BigInt(kept);
  const first = rest.charCodeAt(0) - 48;
  const tail = /[1-9]/.test(rest.slice(1));
  if (first > 5 || (first === 5 && tail) || (first === 5 && !tail && n % 2n === 1n)) n += 1n;
  const value = Number(n) / 10 ** digits;
  return negative ? -value : value;       // -0.04 rounds to -0, as in Python
}

/** The value as the pipeline writes it: Python's f"{x:.Nf}", so -0.04 is "-0.0". */
export function fixed(x: number, digits: number): string {
  const v = roundHalfEven(x, digits);
  const sign = v < 0 || Object.is(v, -0) ? "-" : "";
  return sign + Math.abs(v).toFixed(digits);
}
