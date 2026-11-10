import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import App from "./app";
import { ThemeProvider } from "@/theme-provider";

vi.mock("@/components/chat/chat", () => ({
  Chat: () => <div data-testid="chat" />,
}));

vi.mock("@/lib/api", () => ({
  ApiError: class extends Error {},
  getHealth: async () => ({ status: "ok", agent_model: "x:y" }),
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
  getSettings: async () => ({}),
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
