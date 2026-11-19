import { expect, it } from "vitest";
import { reasoningChoices } from "./reasoning";
import type { ReasoningOption } from "./catalog";

it("offers off when the model declares none or a toggle", () => {
  expect(
    reasoningChoices([{ type: "effort", values: ["none", "low"] }]).map(
      (choice) => choice.value,
    ),
  ).toEqual(["off", "low"]);
  expect(
    reasoningChoices([
      { type: "effort", values: ["low", "max"] },
      { type: "toggle" },
    ]).map((choice) => choice.value),
  ).toEqual(["off", "low", "max"]);
  expect(
    reasoningChoices([{ type: "effort", values: ["low", "high"] }]).map(
      (choice) => choice.value,
    ),
  ).toEqual(["low", "high"]);
});

it("handles toggle-only and budget-only models", () => {
  expect(reasoningChoices([{ type: "toggle" }]).map((choice) => choice.value)).toEqual([
    "off",
    "on",
  ]);
  const budget: ReasoningOption[] = [{ type: "budget_tokens", min: 1024 }];
  expect(reasoningChoices(budget).map((choice) => choice.value)).toEqual([
    "off",
    "low",
    "medium",
    "high",
  ]);
  expect(reasoningChoices([])).toEqual([]);
});

it("labels the effort values for display", () => {
  expect(reasoningChoices([{ type: "effort", values: ["xhigh"] }])).toEqual([
    { value: "xhigh", label: "Extra high" },
  ]);
});
