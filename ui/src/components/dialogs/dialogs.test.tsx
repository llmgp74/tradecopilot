import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { ProfileDialog } from "./profile";
import { SettingsDialog } from "./settings";
import { ThemeProvider } from "@/theme-provider";
import { baseProfile, baseSettings } from "@/test/fixtures";
import { patchSettings } from "@/lib/api";

vi.mock("@/lib/api", () => ({
  ApiError: class extends Error {},
  getProfile: async () => baseProfile,
  patchProfile: async (patch: object) => ({ ...baseProfile, ...patch }),
  getSettings: async () => ({ ...baseSettings, alpaca_base_url: "" }),
  patchSettings: vi.fn(async (patch: object) => ({ ...baseSettings, ...patch })),
  putProvider: vi.fn(async () => baseSettings),
  deleteProvider: vi.fn(async () => baseSettings),
}));

vi.mock("@/lib/catalog", () => ({
  SUPPORTED_NPM: new Set([
    "@ai-sdk/openai",
    "@ai-sdk/openai-compatible",
    "@ai-sdk/anthropic",
    "@ai-sdk/google",
  ]),
  loadModelCatalog: async () => ({
    catalog: { providers: {} },
    source: "builtin" as const,
  }),
}));

it("keeps typed list separators in the profile form", async () => {
  render(
    <ThemeProvider>
      <ProfileDialog open onOpenChange={() => {}} />
    </ThemeProvider>,
  );

  const field = await screen.findByLabelText(/sector exclusions/i);
  await userEvent.clear(field);
  await userEvent.type(field, "Energy, Utilities");

  expect(field).toHaveValue("Energy, Utilities");
});

it("opens on the requested section", async () => {
  render(
    <ThemeProvider>
      <SettingsDialog open initialSection="broker" onOpenChange={() => {}} />
    </ThemeProvider>,
  );

  expect(await screen.findByLabelText(/^alpaca key$/i)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Broker" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Model Providers" })).toBeInTheDocument();
});

it("fills the default Alpaca base URL", async () => {
  render(
    <ThemeProvider>
      <SettingsDialog open initialSection="broker" onOpenChange={() => {}} />
    </ThemeProvider>,
  );

  expect(await screen.findByLabelText(/^alpaca base url$/i)).toHaveValue(
    "https://paper-api.alpaca.markets/v2",
  );
});

it("guards the settings dialog close while edits are pending", async () => {
  const onOpenChange = vi.fn();
  render(
    <ThemeProvider>
      <SettingsDialog open onOpenChange={onOpenChange} />
    </ThemeProvider>,
  );

  await userEvent.click(screen.getByRole("button", { name: "Broker" }));
  const field = await screen.findByLabelText(/^alpaca key$/i);
  await userEvent.type(field, "x");
  await userEvent.keyboard("{Escape}");

  expect(await screen.findByText(/discard unsaved changes/i)).toBeInTheDocument();
  expect(onOpenChange).not.toHaveBeenCalledWith(false);
});

it("confirms before switching away from a dirty section", async () => {
  render(
    <ThemeProvider>
      <SettingsDialog open initialSection="broker" onOpenChange={() => {}} />
    </ThemeProvider>,
  );

  const field = await screen.findByLabelText(/^alpaca key$/i);
  await userEvent.clear(field);
  await userEvent.type(field, "abc");
  await userEvent.click(screen.getByRole("button", { name: "Data Providers" }));

  expect(await screen.findByText(/discard unsaved changes/i)).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Discard" }));

  expect(await screen.findByLabelText(/^fmp api key$/i)).toBeInTheDocument();
});

it("saves the current section without closing", async () => {
  const onOpenChange = vi.fn();
  render(
    <ThemeProvider>
      <SettingsDialog open initialSection="broker" onOpenChange={onOpenChange} />
    </ThemeProvider>,
  );

  const field = await screen.findByLabelText(/^alpaca key$/i);
  await userEvent.clear(field);
  await userEvent.type(field, "new-key");
  await userEvent.click(screen.getByRole("button", { name: "Save section" }));

  await waitFor(() =>
    expect(patchSettings).toHaveBeenCalledWith({ alpaca_api_key: "new-key" }),
  );
  expect(onOpenChange).not.toHaveBeenCalledWith(false);
});
