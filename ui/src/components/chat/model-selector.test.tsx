import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { baseSettings } from "@/test/fixtures";
import { ModelSelector } from "./model-selector";

async function openMenu(name: RegExp) {
  screen.getByRole("button", { name }).focus();
  await userEvent.keyboard("{ArrowDown}");
}

const settings = {
  ...baseSettings,
  providers: [
    baseSettings.providers[0],
    {
      provider_id: "openai",
      api_key: "sk",
      base_url: "",
      npm: "@ai-sdk/openai",
      models: [
        {
          id: "gpt-5",
          name: "GPT-5",
          tool_call: true,
          reasoning_options: [],
        },
      ],
      updated_at: "2026-11-01T00:00:00Z",
    },
  ],
};

it("shows the selected model name", () => {
  render(
    <ModelSelector
      settings={settings}
      provider="deepseek"
      modelId="deepseek-flash"
      disabled={false}
      onChange={() => {}}
      onManage={() => {}}
    />,
  );

  expect(
    screen.getByRole("button", { name: /deepseek v4.1 flash/i }),
  ).toBeInTheDocument();
});

it("shows a logo beside each provider group", async () => {
  render(
    <ModelSelector
      settings={settings}
      provider="openai"
      modelId="gpt-5"
      disabled={false}
      onChange={() => {}}
      onManage={() => {}}
    />,
  );

  await openMenu(/gpt-5/i);

  expect(
    document.querySelector('img[src="https://models.dev/logos/openai.svg"]'),
  ).not.toBeNull();
});

it("lists only configured models grouped by provider", async () => {
  render(
    <ModelSelector
      settings={settings}
      provider="openai"
      modelId="gpt-5"
      disabled={false}
      onChange={() => {}}
      onManage={() => {}}
    />,
  );

  fireEvent.mouseDown(screen.getByRole("button", { name: /gpt-5/i }));

  expect(
    await screen.findByRole("menuitemradio", {
      name: /deepseek v4.1 flash/i,
    }),
  ).toBeInTheDocument();
  expect(screen.getByRole("menuitemradio", { name: /^gpt-5$/i })).toBeInTheDocument();
});

it("reports the chosen provider and model", async () => {
  const onChange = vi.fn();
  render(
    <ModelSelector
      settings={settings}
      provider="openai"
      modelId="gpt-5"
      disabled={false}
      onChange={onChange}
      onManage={() => {}}
    />,
  );

  await openMenu(/gpt-5/i);
  await userEvent.click(
    screen.getByRole("menuitemradio", { name: /deepseek v4.1 flash/i }),
  );

  expect(onChange).toHaveBeenCalledWith("deepseek", "deepseek-flash");
});

it("opens model management from the menu", async () => {
  const onManage = vi.fn();
  render(
    <ModelSelector
      settings={settings}
      provider="deepseek"
      modelId="deepseek-flash"
      disabled={false}
      onChange={() => {}}
      onManage={onManage}
    />,
  );

  await openMenu(/deepseek v4.1 flash/i);
  await userEvent.click(screen.getByRole("menuitem", { name: /manage models/i }));

  expect(onManage).toHaveBeenCalled();
});

it("reads Set model when nothing is selected", () => {
  render(
    <ModelSelector
      settings={{ ...settings, providers: [] }}
      provider=""
      modelId=""
      disabled={false}
      onChange={() => {}}
      onManage={() => {}}
    />,
  );

  expect(screen.getByRole("button", { name: /set model/i })).toBeInTheDocument();
});

it("is disabled while a turn streams", () => {
  render(
    <ModelSelector
      settings={settings}
      provider="deepseek"
      modelId="deepseek-flash"
      disabled
      onChange={() => {}}
      onManage={() => {}}
    />,
  );

  expect(screen.getByRole("button", { name: /deepseek v4.1 flash/i })).toBeDisabled();
});
