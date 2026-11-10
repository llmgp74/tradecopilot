import type { AppSettings, AppSettingsPatch } from "./api";

/** Fields rendered as password inputs. */
export const SECRET_FIELDS: ReadonlySet<keyof AppSettings> = new Set<keyof AppSettings>([
  "model_api_key",
  "alpaca_api_key",
  "alpaca_api_secret",
  "fmp_api_key",
  "finnhub_api_key",
  "fred_api_key",
  "exa_api_key",
]);

/** Writable setting keys, excluding the server-managed timestamp. */
const WRITABLE = [
  "agent_model",
  "model_api_key",
  "alpaca_api_key",
  "alpaca_api_secret",
  "alpaca_base_url",
  "fmp_api_key",
  "finnhub_api_key",
  "fred_api_key",
  "edgar_user_agent",
  "exa_api_key",
] as const;

/**
 * Builds a patch of changed settings only.
 *
 * Sending the whole form would copy environment-provided values into SQLite
 * and stop later environment changes from applying. A cleared field is sent
 * as an empty string, which restores the environment fallback.
 *
 * @param original - Effective settings from the server.
 * @param draft - Edited form values.
 * @returns The partial update.
 */
export function settingsChanges(
  original: AppSettings,
  draft: AppSettings,
): AppSettingsPatch {
  const patch: AppSettingsPatch = {};
  for (const key of WRITABLE) {
    if (draft[key] !== original[key]) {
      patch[key] = draft[key];
    }
  }
  return patch;
}
