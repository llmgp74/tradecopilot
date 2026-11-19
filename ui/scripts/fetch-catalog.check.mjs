import test from "node:test";
import assert from "node:assert/strict";
import { slimCatalog } from "./fetch-catalog.mjs";

test("keeps only the fields the app renders", () => {
  const slim = slimCatalog(
    JSON.stringify({
      openai: {
        id: "openai",
        name: "OpenAI",
        doc: "https://platform.openai.com/docs",
        api: "",
        npm: "@ai-sdk/openai",
        env: ["OPENAI_API_KEY"],
        models: {
          "gpt-5": {
            id: "gpt-5",
            name: "GPT-5",
            reasoning: true,
            tool_call: true,
            reasoning_options: [{ type: "effort", values: ["low", "high"] }],
            cost: { input: 1 },
          },
        },
      },
    }),
  );

  assert.deepEqual(Object.keys(slim.providers), ["openai"]);
  assert.equal(slim.providers.openai.name, "OpenAI");
  assert.equal(slim.providers.openai.models["gpt-5"].name, "GPT-5");
  assert.equal("env" in slim.providers.openai, false);
  assert.equal("cost" in slim.providers.openai.models["gpt-5"], false);
});

test("keeps model ids with colons verbatim", () => {
  const slim = slimCatalog(
    JSON.stringify({
      openrouter: {
        name: "OpenRouter",
        doc: "",
        api: "https://openrouter.ai/api/v1",
        npm: "@ai-sdk/openai-compatible",
        models: { "anthropic/claude:thinking": { name: "Claude", tool_call: true } },
      },
    }),
  );

  assert.ok(slim.providers.openrouter.models["anthropic/claude:thinking"]);
});
