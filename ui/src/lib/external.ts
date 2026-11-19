import { openUrl } from "@tauri-apps/plugin-opener";
import { isTauri } from "./api-base";

/**
 * Opens a URL in the system browser.
 *
 * Inside the desktop shell the opener plugin keeps the page out of the app's
 * webview; in a browser tab it opens a new tab.
 *
 * @param url - Absolute URL.
 */
export async function openExternal(url: string): Promise<void> {
  if (isTauri()) {
    await openUrl(url);
    return;
  }
  window.open(url, "_blank", "noopener,noreferrer");
}
