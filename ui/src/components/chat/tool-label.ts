/** Labels for the compact tool call rows. */

/** Purpose text is capped so one row stays one line. */
const PURPOSE_LIMIT = 80;

/**
 * Reads a non-empty string argument.
 *
 * @param input - Tool arguments, possibly still streaming or malformed.
 * @param key - Argument name.
 * @returns The trimmed value, or null when it is absent or not a string.
 */
function arg(input: unknown, key: string): string | null {
  if (input === null || typeof input !== "object") {
    return null;
  }
  const value = (input as Record<string, unknown>)[key];
  if (typeof value !== "string") {
    return null;
  }
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

/**
 * Collapses a model-written purpose to one short line.
 *
 * @param purpose - Raw purpose argument.
 * @returns The label, or null when the model gave nothing usable.
 */
function purposeLabel(purpose?: string): string | null {
  if (typeof purpose !== "string") {
    return null;
  }
  const oneLine = purpose.replace(/\s+/g, " ").trim();
  return oneLine.length > 0 ? oneLine.slice(0, PURPOSE_LIMIT) : null;
}

/**
 * Returns the last path segment of a file argument.
 *
 * @param input - Tool arguments.
 * @param key - Argument holding the path.
 * @returns The file name, or null.
 */
function fileName(input: unknown, key: string): string | null {
  const path = arg(input, key);
  if (path === null) {
    return null;
  }
  const segments = path.split(/[\\/]+/).filter(Boolean);
  return segments.length > 0 ? segments[segments.length - 1] : null;
}

/**
 * Summarizes the tickers in a proposed ticket.
 *
 * @param input - Tool arguments carrying `legs`.
 * @returns The two first tickers plus a remainder count, or null.
 */
function ticketTickers(input: unknown): string | null {
  if (input === null || typeof input !== "object") {
    return null;
  }
  const legs = (input as Record<string, unknown>).legs;
  if (!Array.isArray(legs)) {
    return null;
  }
  const tickers: string[] = [];
  for (const leg of legs) {
    const ticker = arg(leg, "ticker");
    if (ticker !== null) {
      tickers.push(ticker);
    }
  }
  if (tickers.length === 0) {
    return null;
  }
  const shown = tickers.slice(0, 2).join(", ");
  const rest = tickers.length - 2;
  return rest > 0 ? `${shown} +${rest}` : shown;
}

/** Plural labels for tools that commonly repeat in one turn. */
const PLURAL_LABELS: Record<string, (count: number) => string> = {
  get_quote: (count) => `Checked ${count} prices`,
  get_bars: (count) => `Fetched history for ${count} tickers`,
  get_news: (count) => `Read news for ${count} tickers`,
  get_fundamentals: (count) => `Looked up ${count} companies`,
};

/** Tickers shown before the rest are counted. */
const GROUP_TICKER_LIMIT = 6;

/**
 * Collects the unique tickers of a group's calls.
 *
 * @param inputs - Arguments of every call in the group.
 * @returns The tickers in call order.
 */
function groupTickers(inputs: unknown[]): string[] {
  const tickers: string[] = [];
  for (const input of inputs) {
    const ticker = arg(input, "ticker");
    if (ticker !== null && !tickers.includes(ticker)) {
      tickers.push(ticker);
    }
  }
  return tickers;
}

/**
 * Returns the one-line label for a tool call.
 *
 * The model-written purpose wins when present. Otherwise the label comes from
 * the arguments; the variable part is dropped when its argument is missing.
 *
 * @param name - Raw tool name.
 * @param input - Tool arguments.
 * @param purpose - Optional model-written purpose.
 * @returns The row text, never the raw tool name.
 */
export function rowLabel(name: string, input: unknown, purpose?: string): string {
  const written = purposeLabel(purpose);
  if (written !== null) {
    return written;
  }
  const ticker = arg(input, "ticker");
  const file = fileName(input, "file_path");
  switch (name) {
    case "get_quote":
      return ticker === null ? "Check price" : `Check ${ticker} price`;
    case "get_bars":
      return ticker === null ? "Fetch price history" : `Fetch ${ticker} price history`;
    case "get_fundamentals":
      return ticker === null ? "Look up fundamentals" : `Look up ${ticker} fundamentals`;
    case "get_filings":
      return ticker === null ? "Read filings" : `Read ${ticker} filings`;
    case "get_news":
      return ticker === null ? "Read news" : `Read ${ticker} news`;
    case "get_xbrl_fact": {
      const tag = arg(input, "tag");
      if (ticker === null || tag === null) {
        return "Verify a financial figure";
      }
      return `Verify ${ticker} ${tag}`;
    }
    case "get_macro": {
      const series = arg(input, "series");
      return series === null ? "Check economic data" : `Check ${series} data`;
    }
    case "web_search": {
      const query = arg(input, "query");
      return query === null ? "Search the web" : `Search: ${query}`;
    }
    case "propose_ticket": {
      const tickers = ticketTickers(input);
      return tickers === null ? "Build a ticket" : `Build a ticket: ${tickers}`;
    }
    case "read_file":
      return file === null ? "Read file" : `Read ${file}`;
    case "write_file":
      return file === null ? "Write file" : `Write ${file}`;
    case "edit_file":
      return file === null ? "Edit file" : `Edit ${file}`;
    case "delete":
      return file === null ? "Delete file" : `Delete ${file}`;
    case "ls":
      return `List ${arg(input, "path") ?? "."}`;
    case "glob": {
      const pattern = arg(input, "pattern");
      return pattern === null ? "Find files" : `Find ${pattern}`;
    }
    case "grep": {
      const pattern = arg(input, "pattern");
      return pattern === null ? "Search files" : `Search ${pattern}`;
    }
    case "execute": {
      const command = arg(input, "command");
      const firstLine = command?.split("\n")[0].trim();
      return firstLine ? `Run ${firstLine}` : "Run command";
    }
    case "task": {
      const description = arg(input, "description");
      return description === null ? "Delegate a subtask" : `Delegate: ${description}`;
    }
    case "get_portfolio":
      return "Review your portfolio";
    case "get_positions":
      return "List open positions";
    case "verify_claims":
      return "Cross-check claims";
    case "get_open_orders":
      return "List working orders";
    case "get_trade_history":
      return "List recent trades";
    case "cancel_orders":
      return "Cancel orders";
    case "execute_ticket":
      return "Place the ticket";
    case "write_todos":
      return "Update plan";
    default:
      return "Run a tool";
  }
}

/**
 * Returns the label for a group of consecutive calls to one tool.
 *
 * Tickered tools name the tickers, so a group row says what was fetched
 * rather than only how many calls ran.
 *
 * @param name - Raw tool name shared by the group.
 * @param inputs - Arguments of every call in the group.
 * @returns The plural label with tickers, or the single label with a count.
 */
export function groupLabel(name: string, inputs: unknown[]): string {
  const plural = PLURAL_LABELS[name];
  if (plural !== undefined) {
    const base = plural(inputs.length);
    const tickers = groupTickers(inputs);
    if (tickers.length === 0) {
      return base;
    }
    const shown = tickers.slice(0, GROUP_TICKER_LIMIT);
    const rest = tickers.length - shown.length;
    const suffix = rest > 0 ? ` +${rest}` : "";
    return `${base}: ${shown.join(", ")}${suffix}`;
  }
  return `${rowLabel(name, undefined)} x${inputs.length}`;
}

/**
 * Converts a tool name to camelCase for the detail panel.
 *
 * @param name - Snake case or plain tool name.
 * @returns The camelCase form.
 */
export function camelName(name: string): string {
  const parts = name.split(/[_-]+/).filter(Boolean);
  if (parts.length === 0) {
    return "";
  }
  const [first, ...rest] = parts;
  const tail = rest
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1).toLowerCase())
    .join("");
  return first.toLowerCase() + tail;
}
