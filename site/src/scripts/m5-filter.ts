// The consistency overview's status buttons: All shows every check; a status shows only its checks
// and its line of the key; pressing the pressed status again goes back to All. The buttons are
// hidden in the page and shown here, so without scripts every card shows and no button does
// nothing. A polite live region says how many checks are shown after each press.
export function start(root: HTMLElement): void {
  const group = root.querySelector<HTMLElement>('[data-m5="filter"]');
  const live = root.querySelector<HTMLElement>('[data-m5="shown"]');
  if (!group || !live) return;
  const buttons = [...group.querySelectorAll<HTMLButtonElement>("button[data-filter]")];
  const cards = [...root.querySelectorAll<HTMLElement>("[data-m5-card]")];
  const keys = [...root.querySelectorAll<HTMLElement>("[data-key]")];
  const template = root.dataset.shown ?? "{n} / {total}";
  const apply = (filter: string) => {
    for (const b of buttons) b.setAttribute("aria-pressed", String(b.dataset.filter === filter));
    let shown = 0;
    for (const c of cards) {
      c.hidden = filter !== "all" && c.dataset.status !== filter;
      if (!c.hidden) shown += 1;
    }
    for (const k of keys) k.hidden = filter !== "all" && k.dataset.key !== filter;
    live.textContent = template.replace("{n}", String(shown)).replace("{total}", String(cards.length));
  };
  for (const b of buttons) {
    b.addEventListener("click", () => {
      const pressed = b.getAttribute("aria-pressed") === "true";
      apply(pressed && b.dataset.filter !== "all" ? "all" : b.dataset.filter!);
    });
  }
  group.hidden = false;
}
