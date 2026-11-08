// The bar's third row scrolls sideways on a narrow screen. Bring the page being read into view, so
// the row says where the reader is without a swipe. Only the row moves, never the page; without
// this script the row starts at its first item.
export function start(): void {
  for (const list of document.querySelectorAll<HTMLElement>("nav[data-strip] ul")) {
    const current = list.querySelector<HTMLElement>('[aria-current="page"]');
    if (!current || list.scrollWidth <= list.clientWidth) continue;
    const item = current.closest("li") ?? current;
    list.scrollLeft = Math.max(0, item.offsetLeft - list.offsetLeft - (list.clientWidth - item.offsetWidth) / 2);
  }
}
