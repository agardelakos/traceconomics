// Each row of the topic bar (the country's topics, the topic's sections, a section's pages) scrolls
// sideways on a narrow screen. Bring the current item into view, so every row says where the
// reader is without a swipe. Only the rows move, never the page; without this script each row
// starts at its first item.
//
// The rows are measured in whatever font has arrived. The site's own fonts can come after this
// runs, and they are wider or narrower than the fallback, so the item would end up off-centre:
// centre again once they are in, except a row the reader has already touched. The reader is
// known by their own input on the row, not by its position: when the fonts make a row narrower
// the browser moves it by itself.
export function start(): void {
  const rows = [...document.querySelectorAll<HTMLElement>(".topic-bar nav ul")];
  const touched = new Set<HTMLElement>();
  const centre = () => {
    for (const list of rows) {
      if (touched.has(list)) continue;
      const current = list.querySelector<HTMLElement>("[aria-current]");
      if (!current || list.scrollWidth <= list.clientWidth) continue;
      const item = current.closest("li") ?? current;
      list.scrollLeft = Math.max(
        0,
        item.offsetLeft - list.offsetLeft - (list.clientWidth - item.offsetWidth) / 2,
      );
    }
  };
  centre();
  if (document.fonts?.status !== "loading") return;
  for (const list of rows)
    for (const kind of ["pointerdown", "wheel", "keydown"])
      list.addEventListener(kind, () => touched.add(list), { once: true, passive: true });
  void document.fonts.ready.then(centre);
}
