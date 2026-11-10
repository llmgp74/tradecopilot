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
    } as JournalOutcome),
  ).toBe("+2.10% alpha");
  expect(outcomeLabel(null)).toBe("Pending");
});
