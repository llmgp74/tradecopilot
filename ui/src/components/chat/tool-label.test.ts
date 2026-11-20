import { expect, it } from "vitest";
import { camelName, groupLabel, rowLabel } from "./tool-label";

it("prefers the model purpose", () => {
  expect(rowLabel("get_quote", { ticker: "SPY" }, "Check entry")).toBe("Check entry");
});

it("normalizes the purpose to one short line", () => {
  const long = `Line one\nline two ${"x".repeat(100)}`;
  const label = rowLabel("get_quote", {}, long);
  expect(label).not.toContain("\n");
  expect(label.length).toBe(80);
});

it.each([
  ["get_quote", { ticker: "SPY" }, "Check SPY price"],
  ["get_bars", { ticker: "SPY" }, "Fetch SPY price history"],
  ["get_fundamentals", { ticker: "SPY" }, "Look up SPY fundamentals"],
  ["get_filings", { ticker: "SPY" }, "Read SPY filings"],
  ["get_news", { ticker: "SPY" }, "Read SPY news"],
  ["get_macro", { series: "CPI" }, "Check CPI data"],
  ["get_xbrl_fact", { ticker: "SPY", tag: "Revenues" }, "Verify SPY Revenues"],
  ["web_search", { query: "Fed minutes" }, "Search: Fed minutes"],
  ["read_file", { file_path: "/tmp/10-Q.pdf" }, "Read 10-Q.pdf"],
  ["write_file", { file_path: "/tmp/a.md" }, "Write a.md"],
  ["edit_file", { file_path: "/tmp/a.md" }, "Edit a.md"],
  ["delete", { file_path: "/tmp/a.md" }, "Delete a.md"],
  ["ls", { path: "/tmp" }, "List /tmp"],
  ["glob", { pattern: "*.tsx" }, "Find *.tsx"],
  ["grep", { pattern: "TODO" }, "Search TODO"],
  ["execute", { command: "npm test\necho done" }, "Run npm test"],
  ["task", { description: "Read the filing" }, "Delegate: Read the filing"],
  ["get_portfolio", {}, "Review your portfolio"],
  ["get_positions", {}, "List open positions"],
  ["verify_claims", {}, "Cross-check claims"],
  ["get_open_orders", {}, "List working orders"],
  ["get_trade_history", {}, "List recent trades"],
  ["cancel_orders", {}, "Cancel orders"],
  ["execute_ticket", {}, "Place the ticket"],
  ["write_todos", {}, "Update plan"],
])("derives a label for %s", (name, input, expected) => {
  expect(rowLabel(name, input, "")).toBe(expected);
});

it("drops the variable part when the argument is missing", () => {
  expect(rowLabel("get_quote", {}, "")).toBe("Check price");
  expect(rowLabel("get_quote", { ticker: 42 }, undefined)).toBe("Check price");
  expect(rowLabel("execute", undefined, "")).toBe("Run command");
});

it("summarizes ticket legs", () => {
  const legs = [{ ticker: "NVDA" }, { ticker: "MSFT" }, { ticker: "AAPL" }];
  expect(rowLabel("propose_ticket", { legs }, "")).toBe("Build a ticket: NVDA, MSFT +1");
  expect(rowLabel("propose_ticket", { legs: [{ ticker: "NVDA" }] }, "")).toBe(
    "Build a ticket: NVDA",
  );
});

it("never shows an unknown tool name", () => {
  expect(rowLabel("custom_thing", { x: 1 }, "")).toBe("Run a tool");
  expect(rowLabel("ExtractedClaims", {}, "")).toBe("Run a tool");
});

it("names group tickers so the row says what was fetched", () => {
  const quotes = [{ ticker: "AAPL" }, { ticker: "MSFT" }, { ticker: "GOOG" }];
  expect(groupLabel("get_quote", quotes)).toBe("Checked 3 prices: AAPL, MSFT, GOOG");
  expect(groupLabel("get_bars", quotes.slice(0, 2))).toBe(
    "Fetched history for 2 tickers: AAPL, MSFT",
  );
  expect(groupLabel("get_news", quotes)).toBe(
    "Read news for 3 tickers: AAPL, MSFT, GOOG",
  );
  expect(groupLabel("get_fundamentals", quotes.slice(0, 2))).toBe(
    "Looked up 2 companies: AAPL, MSFT",
  );
});

it("dedupes tickers and counts the rest", () => {
  const many = [
    { ticker: "AAPL" },
    { ticker: "AAPL" },
    { ticker: "MSFT" },
    { ticker: "GOOG" },
    { ticker: "AMZN" },
    { ticker: "META" },
    { ticker: "NVDA" },
    { ticker: "TSLA" },
  ];
  expect(groupLabel("get_quote", many)).toBe(
    "Checked 8 prices: AAPL, MSFT, GOOG, AMZN, META, NVDA +1",
  );
});

it("falls back to a plain plural label without tickers", () => {
  expect(groupLabel("get_quote", [{}, {}])).toBe("Checked 2 prices");
});

it("names other groups with a count", () => {
  expect(groupLabel("write_todos", [{}, {}, {}])).toBe("Update plan x3");
  expect(groupLabel("read_file", [{}, {}])).toBe("Read file x2");
});

it("converts a tool name to camelCase for the detail panel", () => {
  expect(camelName("get_quote")).toBe("getQuote");
  expect(camelName("get_xbrl_fact")).toBe("getXbrlFact");
  expect(camelName("Task")).toBe("task");
});
