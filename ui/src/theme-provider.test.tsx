import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";
import { ThemeProvider, useTheme } from "./theme-provider";

const listeners: ((event: MediaQueryListEvent) => void)[] = [];
let systemPrefersDark = false;

beforeEach(() => {
  listeners.length = 0;
  systemPrefersDark = false;
  vi.stubGlobal(
    "matchMedia",
    vi.fn().mockImplementation((query: string) => ({
      matches: systemPrefersDark,
      media: query,
      onchange: null,
      addEventListener: (_: string, listener: (event: MediaQueryListEvent) => void) => {
        listeners.push(listener);
      },
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  );
  localStorage.clear();
  document.documentElement.classList.remove("dark");
});

function Control() {
  const { theme, preference, setPreference } = useTheme();
  return (
    <>
      <span data-testid="theme">{theme}</span>
      <span data-testid="preference">{preference}</span>
      <button type="button" onClick={() => setPreference("dark")}>
        Dark
      </button>
      <button type="button" onClick={() => setPreference("system")}>
        System
      </button>
    </>
  );
}

it("defaults to the system theme and tracks changes", async () => {
  render(
    <ThemeProvider>
      <Control />
    </ThemeProvider>,
  );

  expect(screen.getByTestId("preference")).toHaveTextContent("system");
  expect(screen.getByTestId("theme")).toHaveTextContent("light");

  act(() => {
    for (const listener of listeners) {
      listener({ matches: true } as MediaQueryListEvent);
    }
  });

  expect(screen.getByTestId("theme")).toHaveTextContent("dark");
  await waitFor(() =>
    expect(document.documentElement.classList.contains("dark")).toBe(true),
  );
});

it("applies a stored preference and persists a new one", async () => {
  localStorage.setItem("tradecopilot-theme", "light");
  render(
    <ThemeProvider>
      <Control />
    </ThemeProvider>,
  );

  expect(screen.getByTestId("preference")).toHaveTextContent("light");

  await userEvent.click(screen.getByRole("button", { name: "Dark" }));

  await waitFor(() =>
    expect(document.documentElement.classList.contains("dark")).toBe(true),
  );
  expect(localStorage.getItem("tradecopilot-theme")).toBe("dark");

  await userEvent.click(screen.getByRole("button", { name: "System" }));

  expect(screen.getByTestId("preference")).toHaveTextContent("system");
  expect(localStorage.getItem("tradecopilot-theme")).toBe("system");
});
