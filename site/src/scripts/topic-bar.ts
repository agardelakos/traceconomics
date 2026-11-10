// Each row of the topic bar (the country's topics, the topic's sections, a section's pages) scrolls
// sideways on a narrow screen. Bring the current item into view, so every row says where the
// reader is without a swipe. Only the rows move, never the page; without this script each row
// starts at its first item.
export function start(): void {
  for (const list of document.querySelectorAll<HTMLElement>(".topic-bar nav ul")) {
    const current = list.querySelector<HTMLElement>("[aria-current]");
    if (!current || list.scrollWidth <= list.clientWidth) continue;
    const item = current.closest("li") ?? current;
    list.scrollLeft = Math.max(0, item.offsetLeft - list.offsetLeft - (list.clientWidth - item.offsetWidth) / 2);
  }
}
