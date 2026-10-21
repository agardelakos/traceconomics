// Terms that open an explanation (glossary terms, method options). With a mouse, pointing at a
// term shows its explanation and a click goes to its page. On touch screens and from the keyboard
// the button keeps its plain behaviour: pressing it opens the explanation, which holds the link,
// and Escape or a tap elsewhere closes it. Without this script every device gets that behaviour.
const CLOSE_DELAY_MS = 200;   // time to move the pointer from the term into its explanation

export function start(): void {
  if (!matchMedia("(hover: hover) and (pointer: fine)").matches) return;
  if (!("showPopover" in HTMLElement.prototype)) return;
  for (const wrap of document.querySelectorAll<HTMLElement>(".term-wrap")) {
    const button = wrap.querySelector<HTMLButtonElement>("button.term");
    const pop = wrap.querySelector<HTMLElement>("[popover]");
    const link = pop?.querySelector<HTMLAnchorElement>("a");
    if (!button || !pop || !link) continue;
    let timer: number | undefined;
    const open = () => {
      window.clearTimeout(timer);
      if (!pop.matches(":popover-open")) pop.showPopover();
    };
    const close = () => {
      window.clearTimeout(timer);
      timer = window.setTimeout(() => { if (pop.matches(":popover-open")) pop.hidePopover(); }, CLOSE_DELAY_MS);
    };
    for (const el of [button, pop]) {
      el.addEventListener("pointerenter", open);
      el.addEventListener("pointerleave", close);
    }
    // A mouse click (detail > 0) follows the link; Enter or Space (detail 0) opens the popover.
    button.addEventListener("click", (e) => {
      if (e.detail > 0) { e.preventDefault(); location.href = link.href; }
    });
  }
}
