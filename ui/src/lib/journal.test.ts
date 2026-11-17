import { expect, it } from "vitest";
import { journalQuery, outcomeLabel } from "./journal";
import type { JournalOutcome } from "./api";

it("drops empty filters", () => {
  expect(journalQuery({ ticker: " ", status: undefined })).toEqual({});
  expect(journalQuery({ ticker: "NVDA", status: "filled" })).toEqual({
    ticker: "NVDA",
    status: "filled",
  });
});

it("labels outcomes with alpha", () => {
  expect(
    outcomeLabel({
      alpha_pct: 2.1,
      return_pct: 3.2,
      counterfactual: false,
      partial: false,
      observed_at: null,
    } as JournalOutcome),
  ).toBe("+2.10% alpha");
  expect(outcomeLabel(null)).toBe("Pending");
});

it("falls back to the return when alpha is missing", () => {
  expect(
    outcomeLabel({
      counterfactual: true,
      entry_price: 100,
      entry_at: "",
      horizon: "weeks",
      return_pct: 3.2,
      benchmark: "SPY",
      benchmark_return_pct: null,
      alpha_pct: null,
      computed_at: "",
      partial: false,
      observed_at: null,
      legs: [],
    }),
  ).toBe("Counterfactual +3.20% return");
});

it("marks a partial outcome", () => {
  expect(
    outcomeLabel({
      counterfactual: false,
      entry_price: 100,
      entry_at: "",
      horizon: "weeks",
      return_pct: 3.2,
      benchmark: "SPY",
      benchmark_return_pct: 1.0,
      alpha_pct: 2.2,
      computed_at: "",
      partial: true,
      observed_at: null,
      legs: [],
    }),
  ).toBe("+2.20% alpha (partial)");
});
