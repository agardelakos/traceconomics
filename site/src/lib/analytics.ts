// Visit counts: Cloudflare Web Analytics, from the company that already serves the site, so no
// other company sees the traffic. Cookieless and in totals only. The token is public by design
// (every page carries it) and fixed for the site, so the same data still build the same files.
//
// The beacon goes only into release builds (TRACECONOMICS_ANALYTICS=on, set by the release step):
// local builds and tests make no outside requests and don't count our own work.
export const BEACON = "https://static.cloudflareinsights.com/beacon.min.js";
export const TOKEN = "69377b8fcb9c470492b1be77ffc04977";

export function analyticsOn(): boolean {
  return process.env.TRACECONOMICS_ANALYTICS === "on";
}
