// Applies the reader's theme choice before the page is drawn (no flash of the other theme).
// The choice is kept only if the reader picked one with the header's theme switch, which says so
// next to the control; no choice means the device setting. Storage can be blocked: then the
// device setting applies.
(function () {
  try {
    var theme = localStorage.getItem("theme");
    if (theme === "light" || theme === "dark") document.documentElement.setAttribute("data-theme", theme);
  } catch (e) {}
})();
