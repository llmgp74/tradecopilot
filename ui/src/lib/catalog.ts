import { invoke } from "@tauri-apps/api/core";
import { isTauri } from "./api-base";

/** One reasoning control a model accepts. */
export type ReasoningOption =
  | { type: "effort"; values: string[] }
  | { type: "toggle" }
  | { type: "budget_tokens"; min: number; max?: number };

/** One catalog model, reduced to the fields the app renders. */
export interface CatalogModel {
  name: string;
  reasoning: boolean;
  reasoning_options: ReasoningOption[];
  tool_call: boolean;
}

/** One catalog provider. */
export interface CatalogProvider {
  name: string;
  doc: string;
  api: string;
  npm: string;
  models: Record<string, CatalogModel>;
}

/** The slimmed models.dev catalog keyed by provider id. */
export interface ModelCatalog {
  providers: Record<string, CatalogProvider>;
}

/** Provider integrations the backend can construct. Keep in step with the
 * server's `SUPPORTED_NPM` in `tradecopilot_agent.llm`. */
export const SUPPORTED_NPM: ReadonlySet<string> = new Set([
  "@ai-sdk/openai",
  "@ai-sdk/openai-compatible",
  "@ai-sdk/anthropic",
  "@ai-sdk/google",
  "@openrouter/ai-sdk-provider",
]);

/**
 * Parses a catalog body.
 *
 * @param raw - JSON text from the cache or the built-in snapshot.
 * @returns The parsed catalog.
 * @throws Error When the body is not an object with a providers object.
 */
function parseCatalog(raw: string): ModelCatalog {
  const parsed: unknown = JSON.parse(raw);
  if (
    parsed === null ||
    typeof parsed !== "object" ||
    typeof (parsed as ModelCatalog).providers !== "object" ||
    (parsed as ModelCatalog).providers === null
  ) {
    throw new Error("The catalog has no providers.");
  }
  return parsed as ModelCatalog;
}

/**
 * Loads the catalog from the Tauri cache, then the built-in snapshot.
 *
 * Never throws. A corrupt cache or a failed request returns the next source,
 * and the last resort is an empty catalog.
 *
 * @returns The catalog and the source that produced it.
 */
export async function loadModelCatalog(): Promise<{
  catalog: ModelCatalog;
  source: "cache" | "builtin";
}> {
  if (isTauri()) {
    try {
      const cached = await invoke<string | null>("cached_model_catalog");
      if (cached) {
        return { catalog: parseCatalog(cached), source: "cache" };
      }
    } catch {
      // A corrupt cache falls through to the built-in snapshot.
    }
  }
  try {
    const response = await fetch("/models-catalog.json");
    if (response.ok) {
      return { catalog: parseCatalog(await response.text()), source: "builtin" };
    }
  } catch {
    // Offline and no snapshot: return the empty catalog below.
  }
  return { catalog: { providers: {} }, source: "builtin" };
}
