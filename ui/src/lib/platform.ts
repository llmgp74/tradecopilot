import { isTauri } from "./api-base";

/**
 * Detects macOS in the browser and the desktop webview.
 *
 * @returns True when the platform is macOS.
 */
export function isMac(): boolean {
  return typeof navigator !== "undefined" && navigator.userAgent.includes("Mac");
}

/**
 * Names the primary shortcut modifier for the current platform.
 *
 * @returns ``Command`` on macOS and ``Ctrl`` elsewhere.
 */
export function primaryModifier(): string {
  return isMac() ? "Command" : "Ctrl";
}

/**
 * Detects macOS inside the desktop webview.
 *
 * @returns True when the app runs on macOS.
 */
export function isMacDesktop(): boolean {
  return isTauri() && navigator.userAgent.includes("Mac");
}

/**
 * Detects Windows inside the desktop webview.
 *
 * @returns True when the app runs on Windows.
 */
export function isWindowsDesktop(): boolean {
  return isTauri() && navigator.userAgent.includes("Windows");
}
