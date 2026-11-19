/**
 * Downloads the models.dev catalog and writes the slimmed shape the app reads.
 *
 * A failed download keeps the committed snapshot. Only a checkout that has no
 * snapshot and no network writes an empty catalog, which the UI reports.
 */
import { existsSync, readFileSync, renameSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const DEFAULT_SOURCE = "https://models.dev/api.json";
const scriptDir = dirname(fileURLToPath(import.meta.url));

/**
 * Builds one model entry.
 *
 * @param {Record<string, unknown>} model - Catalog model.
 * @returns {Record<string, unknown>} The slim entry.
 */
function slimModel(model) {
  return {
    name: String(model?.name ?? ""),
    reasoning: Boolean(model?.reasoning),
    reasoning_options: Array.isArray(model?.reasoning_options)
      ? model.reasoning_options
      : [],
    tool_call: Boolean(model?.tool_call),
  };
}

/**
 * Sorts object entries by key so regenerated output is byte-identical when
 * the upstream catalog is unchanged.
 *
 * @param {object} object - Source object.
 * @returns {[string, unknown][]} Entries in ascending key order.
 */
function sortedEntries(object) {
  return Object.entries(object).sort(([left], [right]) => (left < right ? -1 : 1));
}

/**
 * Drops every provider and model field the UI does not render.
 *
 * @param {string} raw - Catalog JSON.
 * @returns {{ providers: Record<string, unknown> }} The slim catalog.
 */
export function slimCatalog(raw) {
  const parsed = JSON.parse(raw);
  if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("The catalog is not an object.");
  }
  const providers = {};
  for (const [id, provider] of sortedEntries(parsed)) {
    if (provider === null || typeof provider !== "object") {
      continue;
    }
    const models = {};
    for (const [modelId, model] of sortedEntries(provider.models ?? {})) {
      models[modelId] = slimModel(model);
    }
    providers[id] = {
      name: String(provider.name ?? id),
      doc: String(provider.doc ?? ""),
      api: String(provider.api ?? ""),
      npm: String(provider.npm ?? ""),
      models,
    };
  }
  return { providers };
}

/**
 * Reads the catalog from an HTTP URL or a local file.
 *
 * @param {string} source - URL or path.
 * @returns {Promise<string>} The raw JSON.
 */
async function load(source) {
  if (/^https?:\/\//.test(source)) {
    const response = await fetch(source);
    if (!response.ok) {
      throw new Error(`The catalog fetch failed with ${response.status}.`);
    }
    return response.text();
  }
  return readFileSync(source, "utf8");
}

/**
 * Runs the download and write.
 *
 * @param {string[]} argv - Process arguments.
 * @returns {Promise<void>}
 */
async function main(argv) {
  let source = DEFAULT_SOURCE;
  let output = join(scriptDir, "..", "public", "models-catalog.json");
  for (let index = 0; index < argv.length; index += 1) {
    if (argv[index] === "--source") {
      source = argv[(index += 1)];
    }
    if (argv[index] === "--output") {
      output = resolve(argv[(index += 1)]);
    }
  }
  try {
    const slim = slimCatalog(await load(source));
    const temporary = `${output}.tmp`;
    writeFileSync(temporary, `${JSON.stringify(slim, null, 2)}\n`);
    renameSync(temporary, output);
    console.log(`Wrote ${Object.keys(slim.providers).length} providers to ${output}`);
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    if (existsSync(output)) {
      console.warn(`Catalog refresh failed (${message}); keeping ${output}`);
      return;
    }
    writeFileSync(output, `${JSON.stringify({ providers: {} }, null, 2)}\n`);
    console.warn(`Catalog refresh failed (${message}); wrote an empty catalog`);
  }
}

if (import.meta.url === pathToFileURL(process.argv[1]).href) {
  await main(process.argv.slice(2));
}
