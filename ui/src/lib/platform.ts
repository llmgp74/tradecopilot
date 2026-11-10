import { isTauri } from "./api-base";

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
