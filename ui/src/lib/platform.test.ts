import { afterEach, expect, it, vi } from "vitest";
import { isMacDesktop, isWindowsDesktop } from "./platform";

function stubTauri(): void {
  Object.defineProperty(window, "__TAURI_INTERNALS__", {
    value: {},
    configurable: true,
  });
}

afterEach(() => {
  delete (window as { __TAURI_INTERNALS__?: unknown }).__TAURI_INTERNALS__;
  vi.restoreAllMocks();
});

it("detects macOS inside the desktop webview", () => {
  stubTauri();
  vi.spyOn(navigator, "userAgent", "get").mockReturnValue(
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0)",
  );
  expect(isMacDesktop()).toBe(true);
  expect(isWindowsDesktop()).toBe(false);
});

it("detects Windows inside the desktop webview", () => {
  stubTauri();
  vi.spyOn(navigator, "userAgent", "get").mockReturnValue(
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
  );
  expect(isWindowsDesktop()).toBe(true);
  expect(isMacDesktop()).toBe(false);
});

it("is neither platform outside the desktop webview", () => {
  vi.spyOn(navigator, "userAgent", "get").mockReturnValue(
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0)",
  );
  expect(isMacDesktop()).toBe(false);
  expect(isWindowsDesktop()).toBe(false);
});
