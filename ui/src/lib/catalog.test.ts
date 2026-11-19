import { beforeEach, expect, it, vi } from "vitest";
import { invoke } from "@tauri-apps/api/core";
import { loadModelCatalog } from "./catalog";

const { state } = vi.hoisted(() => ({ state: { tauri: true } }));

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn() }));
vi.mock("./api-base", () => ({ isTauri: () => state.tauri }));

const provider = {
  name: "OpenAI",
  doc: "d",
  api: "",
  npm: "@ai-sdk/openai",
  models: {
    "gpt-5": {
      name: "GPT-5",
      reasoning: true,
      reasoning_options: [{ type: "effort", values: ["low", "high"] }],
      tool_call: true,
    },
  },
};

beforeEach(() => {
  vi.mocked(invoke).mockReset();
  state.tauri = true;
  vi.unstubAllGlobals();
});

it("uses the Tauri cache when present", async () => {
  vi.mocked(invoke).mockResolvedValue(
    JSON.stringify({ providers: { openai: provider } }),
  );

  const result = await loadModelCatalog();

  expect(result.source).toBe("cache");
  expect(result.catalog.providers.openai.name).toBe("OpenAI");
});

it("falls back to the built-in snapshot when the cache is corrupt", async () => {
  vi.mocked(invoke).mockResolvedValue("{bad");
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify({ providers: { openai: provider } }))),
  );

  const result = await loadModelCatalog();

  expect(result.source).toBe("builtin");
  expect(result.catalog.providers.openai.models["gpt-5"].tool_call).toBe(true);
});

it("returns an empty catalog when both sources fail", async () => {
  vi.mocked(invoke).mockRejectedValue(new Error("no cache"));
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => {
      throw new Error("offline");
    }),
  );

  const result = await loadModelCatalog();

  expect(result.source).toBe("builtin");
  expect(result.catalog.providers).toEqual({});
});
