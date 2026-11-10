let base = "";

/** @returns True when the page runs inside the Tauri webview. */
export function isTauri(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

/**
 * Sets the agent origin used for API calls.
 *
 * @param value - Origin such as `http://127.0.0.1:52143`.
 */
export function setApiBase(value: string): void {
  base = value.replace(/\/+$/, "");
}

/** @returns The current agent origin, or an empty string. */
export function getApiBase(): string {
  return base;
}

/** Clears the agent origin. Test hook. */
export function resetApiBase(): void {
  base = "";
}

/**
 * Resolves an API path against the agent origin.
 *
 * @param path - Path beginning with `/api`, or an absolute URL.
 * @returns The URL to fetch.
 */
export function apiUrl(path: string): string {
  if (/^https?:\/\//.test(path)) {
    return path;
  }
  return `${base}${path}`;
}
