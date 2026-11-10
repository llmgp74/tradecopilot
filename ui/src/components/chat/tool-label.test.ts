import { expect, it } from "vitest";
import { toolTitle } from "./tool-label";

it("describes the action in plain language", () => {
  expect(toolTitle("get_bars")).toBe("Fetch price history");
  expect(toolTitle("get_xbrl_fact")).toBe("Verify a reported financial figure");
  expect(toolTitle("execute_ticket")).toBe("Place the trade");
  expect(toolTitle("web_search")).toBe("Search the web");
});

it("humanizes unknown tool names", () => {
  expect(toolTitle("custom_thing")).toBe("Custom thing");
  expect(toolTitle("ExtractedClaims")).toBe("Extracted claims");
});
