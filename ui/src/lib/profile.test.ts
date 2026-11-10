import { expect, it } from "vitest";
import { profileChanges, requiresConfirmation } from "./profile";
import { baseProfile } from "@/test/fixtures";

it("returns only changed fields", () => {
  expect(profileChanges(baseProfile, { ...baseProfile, watchlist: ["NVDA"] })).toEqual({
    watchlist: ["NVDA"],
  });
});

it("flags hard-constraint and execution changes", () => {
  expect(requiresConfirmation({ position_cap_pct: 8 })).toBe(true);
  expect(requiresConfirmation({ sector_exclusions: ["Energy"] })).toBe(true);
  expect(
    requiresConfirmation({ execution: { autonomous: true, max_order_notional: 500 } }),
  ).toBe(true);
  expect(requiresConfirmation({ watchlist: ["NVDA"] })).toBe(false);
});
