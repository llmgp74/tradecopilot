import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import App from "./app";
import { getSettings } from "@/lib/api";
import { ThemeProvider } from "@/theme-provider";
import { baseSettings } from "@/test/fixtures";

vi.mock("@/components/chat/chat", () => ({
  Chat: () => <div data-testid="chat" />,
}));

vi.mock("@/lib/api", () => ({
  ApiError: class extends Error {},
  listThreads: async () => ({ items: [], page_no: 1, page_size: 50, total: 0 }),
  getThread: async () => {
    throw new Error("not used");
  },
  getPortfolio: async () => ({
    as_of: "",
    paper: true,
    account: {
      currency: "USD",
      equity: 0,
      cash: 0,
      buying_power: 0,
      long_market_value: 0,
    },
    day: { pnl: 0, pnl_pct: 0 },
    positions: [],
    equity_curve: [],
  }),
  getProfile: async () => ({}),
  getSettings: vi.fn(async () => baseSettings),
  listJournal: async () => ({ items: [], page_no: 1, page_size: 20, total: 0 }),
  patchProfile: async () => ({}),
  patchSettings: async () => ({}),
}));

it("keeps the chat mounted while a dialog is open", async () => {
  render(
    <ThemeProvider>
      <App />
    </ThemeProvider>,
  );

  await screen.findByTestId("chat");
  await userEvent.click(screen.getByRole("button", { name: "Portfolio" }));

  expect(screen.getByRole("dialog", { name: "Portfolio" })).toBeInTheDocument();
  expect(screen.getByTestId("chat")).toBeInTheDocument();
});

it("opens settings on the broker section from the status chip", async () => {
  render(
    <ThemeProvider>
      <App />
    </ThemeProvider>,
  );

  await screen.findByTestId("chat");
  await userEvent.click(await screen.findByRole("button", { name: "Alpaca" }));

  expect(await screen.findByLabelText(/^alpaca key$/i)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Broker" })).toHaveAttribute(
    "aria-current",
    "page",
  );
});

it("refreshes settings after the dialog closes", async () => {
  render(
    <ThemeProvider>
      <App />
    </ThemeProvider>,
  );

  await screen.findByTestId("chat");
  await waitFor(() => expect(getSettings).toHaveBeenCalledTimes(1));
  await userEvent.click(screen.getByRole("button", { name: "Settings" }));
  await waitFor(() => expect(getSettings).toHaveBeenCalledTimes(2));
  await userEvent.keyboard("{Escape}");

  await waitFor(() => expect(getSettings).toHaveBeenCalledTimes(3));
});
