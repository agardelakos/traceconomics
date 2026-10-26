// The header's theme setting: device setting, light or dark. A choice of light or dark is kept in
// this browser (localStorage, one value, never sent anywhere), so it holds from page to page;
// "device setting" removes it. The control says so next to the options: under EU guidance a
// preference remembered for longer than a session needs that notice (no banner). The page head
// applies the stored value before drawing (public/theme.js).
const KEY = "theme";
type Theme = "system" | "light" | "dark";

function stored(): Theme {
  try {
    const v = localStorage.getItem(KEY);
    return v === "light" || v === "dark" ? v : "system";
  } catch {
    return "system";
  }
}

function apply(theme: Theme) {
  const root = document.documentElement;
  if (theme === "system") root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", theme);
  try {
    if (theme === "system") localStorage.removeItem(KEY);
    else localStorage.setItem(KEY, theme);
  } catch {
    // Storage blocked: the choice holds on this page only.
  }
}

export function start(boxes: HTMLElement[]) {
  // The same choice can be shown twice (the settings button, and the phone menu): every copy
  // shows the current value and changes with the others.
  const radios = boxes.flatMap((box) => [...box.querySelectorAll<HTMLInputElement>('input[type="radio"]')]);
  const show = (theme: Theme) => { for (const r of radios) r.checked = r.value === theme; };
  show(stored());
  for (const r of radios) {
    r.addEventListener("change", () => {
      if (!r.checked) return;
      apply(r.value as Theme);
      show(r.value as Theme);
    });
  }
  // Without a script the switch can't work, so it stays hidden until now.
  for (const box of boxes) box.hidden = false;
}
