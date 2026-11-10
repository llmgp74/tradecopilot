/** Plain-language labels for the agent tools. */
const TOOL_TITLES: Record<string, string> = {
  get_quote: "Check the current price",
  get_bars: "Fetch price history",
  get_portfolio: "Review your portfolio",
  get_positions: "List your open positions",
  get_fundamentals: "Look up company fundamentals",
  get_filings: "Find recent SEC filings",
  get_xbrl_fact: "Verify a reported financial figure",
  get_news: "Read recent company news",
  get_macro: "Check economic data",
  web_search: "Search the web",
  verify_claims: "Verify the answer's claims",
  propose_ticket: "Draft a trade ticket",
  execute_ticket: "Place the trade",
  write_todos: "Outline the steps",
};

/**
 * Turns a raw tool identifier into a sentence-case label.
 *
 * @param name - Snake case or camel case tool name.
 * @returns The humanized label.
 */
function humanize(name: string): string {
  const spaced = name
    .replace(/[_-]+/g, " ")
    .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
    .trim()
    .toLowerCase();
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

/**
 * Returns the display label for a tool name.
 *
 * @param name - Raw tool name.
 * @returns A short action phrase, or a humanized unknown name.
 */
export function toolTitle(name: string): string {
  return TOOL_TITLES[name] ?? humanize(name);
}
