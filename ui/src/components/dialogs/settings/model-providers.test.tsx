import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";
import { invoke } from "@tauri-apps/api/core";
import { deleteProvider, putProvider } from "@/lib/api";
import { loadModelCatalog, type ModelCatalog } from "@/lib/catalog";
import { baseSettings } from "@/test/fixtures";
import { ModelProvidersSection } from "./model-providers";

const { flags } = vi.hoisted(() => ({ flags: { tauri: false } }));

vi.mock("@/lib/api-base", () => ({ isTauri: () => flags.tauri }));
vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn() }));
vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...actual, putProvider: vi.fn(), deleteProvider: vi.fn() };
});
vi.mock("@/lib/catalog", async () => {
  const actual = await vi.importActual<typeof import("@/lib/catalog")>("@/lib/catalog");
  return { ...actual, loadModelCatalog: vi.fn() };
});

const catalog: ModelCatalog = {
  providers: {
    deepseek: {
      name: "DeepSeek",
      doc: "",
      api: "https://api.deepseek.com",
      npm: "@ai-sdk/openai-compatible",
      models: {
        "deepseek-flash": {
          name: "DeepSeek V4.1 Flash",
          reasoning: true,
          reasoning_options: [{ type: "toggle" }],
          tool_call: true,
        },
      },
    },
    openai: {
      name: "OpenAI",
      doc: "",
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
    },
    azure: {
      name: "Azure OpenAI",
      doc: "",
      api: "",
      npm: "@ai-sdk/azure",
      models: {},
    },
  },
};

beforeEach(() => {
  flags.tauri = false;
  vi.mocked(loadModelCatalog).mockResolvedValue({
    catalog,
    source: "builtin",
  });
  vi.mocked(putProvider).mockResolvedValue(baseSettings);
  vi.mocked(deleteProvider).mockResolvedValue(baseSettings);
  vi.mocked(invoke).mockReset();
});

function renderSection() {
  const onSaved = vi.fn();
  const onDirtyChange = vi.fn();
  render(
    <ModelProvidersSection
      settings={baseSettings}
      onSaved={onSaved}
      onDirtyChange={onDirtyChange}
    />,
  );
  return { onSaved, onDirtyChange };
}

it("lists configured providers first and disables unsupported ones", async () => {
  renderSection();

  expect(await screen.findByRole("button", { name: "DeepSeek" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Azure OpenAI" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "OpenAI" })).toBeEnabled();
});

it("saves the whole provider draft", async () => {
  renderSection();

  await userEvent.click(await screen.findByRole("button", { name: "DeepSeek" }));
  const key = screen.getByLabelText(/^api key$/i);
  await userEvent.clear(key);
  await userEvent.type(key, "new-key");
  await userEvent.click(screen.getByRole("button", { name: "Save provider" }));

  await waitFor(() =>
    expect(putProvider).toHaveBeenCalledWith("deepseek", {
      api_key: "new-key",
      base_url: "",
      npm: "@ai-sdk/openai-compatible",
      models: baseSettings.providers[0].models,
    }),
  );
});

it("warns that removing the selected model clears the selection", async () => {
  renderSection();

  await userEvent.click(await screen.findByRole("button", { name: "DeepSeek" }));
  await userEvent.click(
    screen.getByRole("button", { name: "Remove DeepSeek V4.1 Flash" }),
  );

  expect(screen.getByText(/clears the selection/i)).toBeInTheDocument();
  expect(screen.getByText(/no models selected/i)).toBeInTheDocument();
});

it("adds a provider from the catalog search", async () => {
  renderSection();

  await userEvent.click(await screen.findByRole("button", { name: "Add provider" }));
  await userEvent.type(screen.getByLabelText(/search providers/i), "openai");
  await userEvent.click(screen.getByRole("button", { name: "OpenAI" }));

  expect(screen.getByRole("heading", { name: "OpenAI" })).toBeInTheDocument();
  expect(screen.getByText(/no models selected/i)).toBeInTheDocument();
});

it("keeps configured providers when the catalog is empty", async () => {
  vi.mocked(loadModelCatalog).mockResolvedValue({
    catalog: { providers: {} },
    source: "builtin",
  });
  renderSection();

  expect(await screen.findByRole("button", { name: "deepseek" })).toBeInTheDocument();
});

it("disables the default reasoning row when the selected model has no options", async () => {
  const provider = baseSettings.providers[0];
  const settings = {
    ...baseSettings,
    providers: [
      {
        ...provider,
        models: [{ ...provider.models[0], reasoning_options: [] }],
      },
    ],
  };
  render(
    <ModelProvidersSection
      settings={settings}
      onSaved={vi.fn()}
      onDirtyChange={vi.fn()}
    />,
  );

  expect(await screen.findByLabelText(/default reasoning/i)).toBeDisabled();
});

it("refreshes the catalog under Tauri", async () => {
  flags.tauri = true;
  renderSection();

  await userEvent.click(await screen.findByRole("button", { name: "Refresh catalog" }));

  await waitFor(() => expect(invoke).toHaveBeenCalledWith("refresh_model_catalog"));
  expect(vi.mocked(loadModelCatalog)).toHaveBeenCalledTimes(2);
});
