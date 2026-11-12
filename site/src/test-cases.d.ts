// A Vitest test's case: its stable ID and its Given/When/Then, in the test's `meta` option, so the case
// is written on the test it describes. The test catalog reads it from Vitest's JSON report (which
// vitest.config.ts writes on every run); Vitest's own listing leaves `meta` out.
//
//   test("…", { meta: { id: "VT-FMT-001", given: "…", when: "…", then: ["…", "…"] } }, () => { … });
//
// A string or a list of strings per step; a list continues the step ("And …"). A test made per value
// (`test.each`, a loop) passes the same case: one ID, the values are its examples.
import "vitest";

declare module "vitest" {
  interface TaskMeta {
    id?: string;
    title?: string; // when the test's own title is a loop's value
    given?: string | string[];
    when?: string | string[];
    then?: string | string[];
  }
}
