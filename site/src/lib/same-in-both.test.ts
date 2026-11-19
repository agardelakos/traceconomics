// The two-build check: figures that read the same whatever the data.
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { pageText, sameInBoth, sameOnPage } from "./same-in-both.mjs";

const page = (body: string) =>
  `<html><head><style>.x{width:50%}</style></head><body>${body}<script>const y = "7.5%";</script></body></html>`;

describe("figures that read the same with other data", () => {
  it(
    "reads what a reader sees or hears: text and labels, not scripts or styles",
    {
      meta: {
        id: "VT-SAME-001",
        given:
          "a page with a figure in its text, one in an aria-label, one in a title, and others in a script and a style",
        when: "its text is read",
        then: "the text and both attributes are read, with entities decoded, and the script and style are not",
      },
    },
    () => {
      const text = pageText(
        page(
          '<p>Rose 4.9&#160;%</p><svg aria-label="Poorest fifth 5.1%"><title>x</title></svg><abbr title="2.0 points">pp</abbr>',
        ),
      );
      expect(text).toContain("Rose 4.9 %");
      expect(text).toContain("Poorest fifth 5.1%");
      expect(text).toContain("2.0 points");
      expect(text).not.toContain("7.5%");
      expect(text).not.toContain("50%");
    },
  );

  it(
    "compares figures place by place, and names the ones that didn't change and aren't explained",
    {
      meta: {
        id: "VT-SAME-002",
        given:
          "two builds of a page: the same number of figures, one of them unchanged; then a different number of figures; and a figure typed in the text",
        when: "the figures that read the same are found",
        then: [
          "an unchanged figure in the same place is named, one that only moved place is not",
          "with a different number of figures, any figure of the first build that the second shows is named",
          "a figure explained (typed in the text, or allowed) is never named",
        ],
      },
    },
    () => {
      const a = page("<p>4.9%</p><p>9.4%</p><p>2.0%</p>");
      expect(sameOnPage(a, page("<p>5.3%</p><p>9.4%</p><p>4.9%</p>"))).toEqual(["9.4%"]);
      expect(sameOnPage(a, page("<p>4.9%</p><p>1.0%</p>"))).toEqual(["4.9%"]);
      expect(sameOnPage(a, page("<p>5.3%</p><p>9.4%</p><p>4.9%</p>"), new Set(["9.4%"]))).toEqual(
        [],
      );
    },
  );

  it(
    "goes through every page of both builds and names the pages only one has",
    {
      meta: {
        id: "VT-SAME-003",
        given:
          "two builds: a page whose figure changed, one with a figure that didn't, and a page in the first only",
        when: "the builds are compared",
        then: [
          "the page with the unchanged figure is named with it",
          "the page that only one build has is named as such",
          "the page whose figure changed is not named",
        ],
      },
    },
    () => {
      const root = fs.mkdtempSync(path.join(os.tmpdir(), "same-in-both-"));
      const write = (build: string, rel: string, html: string) => {
        fs.mkdirSync(path.dirname(path.join(root, build, rel)), { recursive: true });
        fs.writeFileSync(path.join(root, build, rel), page(html));
      };
      write("a", "en/index.html", "<p>4.9%</p>");
      write("b", "en/index.html", "<p>5.3%</p>");
      write("a", "en/gr/index.html", "<p>9.4%</p>");
      write("b", "en/gr/index.html", "<p>9.4%</p>");
      write("a", "en/only/index.html", "<p>1%</p>");
      const got = sameInBoth(path.join(root, "a"), path.join(root, "b"));
      expect(got.found).toEqual([{ page: path.join("en", "gr", "index.html"), figures: ["9.4%"] }]);
      expect(got.unmatched).toEqual([path.join("en", "only", "index.html")]);
      fs.rmSync(root, { recursive: true });
    },
  );
});
