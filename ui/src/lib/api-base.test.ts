import { afterEach, expect, it } from "vitest";
import { apiUrl, getApiBase, resetApiBase, setApiBase } from "./api-base";

afterEach(() => resetApiBase());

it("leaves paths relative until a base is set", () => {
  expect(apiUrl("/api/health")).toBe("/api/health");
});

it("prefixes paths with the base", () => {
  setApiBase("http://127.0.0.1:52143/");
  expect(getApiBase()).toBe("http://127.0.0.1:52143");
  expect(apiUrl("/api/health")).toBe("http://127.0.0.1:52143/api/health");
});

it("does not double prefix absolute urls", () => {
  setApiBase("http://127.0.0.1:52143");
  expect(apiUrl("https://example.com/x")).toBe("https://example.com/x");
});
