import { expect, it } from "vitest";
import { SECRET_FIELDS, settingsChanges } from "./settings";
import { baseSettings } from "@/test/fixtures";

it("sends only changed fields", () => {
  expect(settingsChanges(baseSettings, { ...baseSettings, model_id: "gpt-5" })).toEqual({
    model_id: "gpt-5",
  });
});

it("sends a cleared field as an empty string", () => {
  expect(settingsChanges(baseSettings, { ...baseSettings, fmp_api_key: "" })).toEqual({
    fmp_api_key: "",
  });
});

it("does not copy unchanged environment-backed values", () => {
  expect(settingsChanges(baseSettings, { ...baseSettings })).toEqual({});
});

it("marks secret fields", () => {
  expect(SECRET_FIELDS.has("alpaca_api_key")).toBe(true);
  expect(SECRET_FIELDS.has("exa_api_key")).toBe(true);
  expect(SECRET_FIELDS.has("edgar_user_agent")).toBe(false);
});
