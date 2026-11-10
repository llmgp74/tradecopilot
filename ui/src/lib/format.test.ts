import { expect, it } from "vitest";
import { formatPct, formatSignedPct, formatUsd } from "./format";

it("formats money and percentages", () => {
  expect(formatUsd(100000)).toBe("$100,000.00");
  expect(formatPct(1.234)).toBe("1.23%");
  expect(formatSignedPct(2.1)).toBe("+2.10%");
  expect(formatSignedPct(-0.5)).toBe("-0.50%");
});
