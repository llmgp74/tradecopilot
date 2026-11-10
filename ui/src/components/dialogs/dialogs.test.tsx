import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { ProfileDialog } from "./profile";
import { SettingsDialog } from "./settings";
import { ThemeProvider } from "@/theme-provider";
import { baseProfile, baseSettings } from "@/test/fixtures";

vi.mock("@/lib/api", () => ({
  ApiError: class extends Error {},
  getProfile: async () => baseProfile,
  patchProfile: async (patch: object) => ({ ...baseProfile, ...patch }),
  getSettings: async () => baseSettings,
  patchSettings: async (patch: object) => ({ ...baseSettings, ...patch }),
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

it("guards the settings dialog close while edits are pending", async () => {
  const onOpenChange = vi.fn();
  render(
    <ThemeProvider>
      <SettingsDialog open onOpenChange={onOpenChange} />
    </ThemeProvider>,
  );

  const field = await screen.findByLabelText(/provider and model/i);
  await userEvent.type(field, "x");
  await userEvent.keyboard("{Escape}");

  expect(await screen.findByText(/discard unsaved changes/i)).toBeInTheDocument();
  expect(onOpenChange).not.toHaveBeenCalledWith(false);
});

it("toggles one secret field independently", async () => {
  render(
    <ThemeProvider>
      <SettingsDialog open onOpenChange={() => {}} />
    </ThemeProvider>,
  );

  const modelKey = (await screen.findByLabelText(/^Model API key$/i)) as HTMLInputElement;
  const alpacaKey = screen.getByLabelText("Alpaca key") as HTMLInputElement;
  expect(modelKey.type).toBe("password");

  await userEvent.click(screen.getByRole("button", { name: /show model api key/i }));

  expect(modelKey.type).toBe("text");
  expect(alpacaKey.type).toBe("password");
});

it("switches the theme from the settings dialog", async () => {
  localStorage.setItem("tradecopilot-theme", "light");
  render(
    <ThemeProvider>
      <SettingsDialog open onOpenChange={() => {}} />
    </ThemeProvider>,
  );

  await userEvent.click(await screen.findByRole("combobox", { name: /theme/i }));
  await userEvent.click(await screen.findByRole("option", { name: "Dark" }));

  await waitFor(() =>
    expect(document.documentElement.classList.contains("dark")).toBe(true),
  );
  expect(localStorage.getItem("tradecopilot-theme")).toBe("dark");
});
