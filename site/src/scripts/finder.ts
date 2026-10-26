// The group finder on the Groups page: from who lives in a household, its net income, its home and
// its main income, which of the site's groups it belongs to. Everything stays in the page: there
// is no form to send, nothing is stored, and the links it offers carry only the groups, never the
// income.

import { fill, num, type Lang } from "../lib/format";
import { equivalentSize, parseAmount, placeIncome } from "../lib/income";

interface Config {
  lang: Lang;
  cutoffs: Record<string, number>;
  names: Record<string, string>;      // group key -> its name
  inNames: Record<string, string>;    // group key -> its name inside a sentence
  calculator: string;                 // the calculator's address
  explore: string;                    // Explore's address
  text: Record<string, string>;
}

export function startFinder(root: HTMLElement): void {
  const cfg: Config = JSON.parse(root.dataset.finder!);
  const $ = <T extends HTMLElement>(role: string) => root.querySelector<T>(`[data-find="${role}"]`)!;
  const value = (name: string) => root.querySelector<HTMLInputElement>(`input[name="${name}"]:checked`)?.value ?? null;

  // A number box the reader is still typing in may be empty or out of range: keep it within
  // bounds for the sums, and leave the box itself alone.
  const count = (input: HTMLInputElement, lo: number) => {
    const v = Math.round(Number(input.value));
    return Number.isFinite(v) ? Math.min(Math.max(v, lo), Number(input.max)) : lo;
  };

  const link = (base: string, param: string, v: string) => {
    const u = new URL(base, location.href);
    u.searchParams.set(param, v);
    return u.pathname + u.search;
  };

  const draw = () => {
    const size = equivalentSize(count($<HTMLInputElement>("older"), 1), count($<HTMLInputElement>("children"), 0));
    $("size").textContent = fill(cfg.text.size, { size: num(cfg.lang, size) });

    const amount = parseAmount($<HTMLInputElement>("income").value);
    const yearly = amount === null ? null : value("per") === "month" ? amount * 12 : amount;
    const place = yearly === null || yearly <= 0 ? null : placeIncome(cfg.cutoffs, size, yearly);

    const home = value("home");
    const pension = value("pension");
    const groups: { calc: string; explore: string }[] = [];
    if (place) groups.push({ calc: `B/${place.fifth}`, explore: place.fifth });
    if (home) groups.push({ calc: `tenure/${home}`, explore: `tenure/${home}` });
    if (pension) {
      const k = pension === "yes" ? "pensioners/pensioners" : "pensioners/other";
      groups.push({ calc: k, explore: k });
    }

    $("empty").hidden = place !== null;
    $("income-row").hidden = place === null;
    if (place) $("income-value").textContent = cfg.names[place.fifth];
    $("near").hidden = !place?.neighbour;
    if (place?.neighbour) $("near").textContent = fill(cfg.text.near, { group: cfg.inNames[place.neighbour] });
    $("home-row").hidden = home === null;
    if (home) $("home-value").textContent = cfg.names[`tenure/${home}`];
    $("pension-row").hidden = pension === null;
    if (pension) $("pension-value").textContent = cfg.names[pension === "yes" ? "pensioners/pensioners" : "pensioners/other"];

    const next = $("next");
    next.hidden = groups.length === 0;
    $("starts").replaceChildren(...groups.map((g) => {
      const a = Object.assign(document.createElement("a"), { className: "button", href: link(cfg.calculator, "from", g.calc), textContent: cfg.names[g.explore] });
      const li = document.createElement("li");
      li.append(a);
      return li;
    }));
    $<HTMLAnchorElement>("compare").href = link(cfg.explore, "groups", groups.map((g) => g.explore).join(","));
  };

  root.addEventListener("change", draw);
  root.addEventListener("input", draw);
  $("form").hidden = false;
  $("noscript").hidden = true;
  draw();
}
