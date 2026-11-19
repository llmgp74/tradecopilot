import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";
import { PortfolioDialog } from "./portfolio";

const { getPortfolio } = vi.hoisted(() => ({ getPortfolio: vi.fn() }));

const positions = Array.from({ length: 7 }, (_, index) => ({
  ticker: `T${index + 1}`,
  sector: "Technology",
  qty: 1,
  avg_entry_price: 100,
  current_price: 100,
  market_value: (index + 1) * 1000,
  unrealized_pl: 0,
  unrealized_pl_pct: 0,
  weight_pct: (index + 1) / 10,
}));

vi.mock("@/lib/api", () => ({ getPortfolio }));

function portfolioFor(range: string) {
  return {
    as_of: "2026-11-19T00:00:00Z",
    paper: true,
    account: {
      currency: "USD",
      equity: 28000,
      cash: 0,
      buying_power: 0,
      long_market_value: 28000,
    },
    day: { pnl: 0, pnl_pct: 0 },
    positions,
    equity_curve: [{ t: "2026-11-18T00:00:00Z", equity: range === "1W" ? 27000 : 28000 }],
  };
}

beforeEach(() => {
  getPortfolio.mockImplementation(async (range: string) => portfolioFor(range));
});

it("lists the five largest holdings and links to Alpaca", async () => {
  render(<PortfolioDialog open onOpenChange={() => {}} />);

  expect(await screen.findByText("T7")).toBeInTheDocument();
  expect(screen.getByText("T3")).toBeInTheDocument();
  expect(screen.queryByText("T2")).toBeNull();
  expect(screen.getByText(/showing the 5 largest of 7 holdings/i)).toBeInTheDocument();

  const link = screen.getByRole("link", { name: /view portfolio/i });
  expect(link).toHaveAttribute("href", "https://app.alpaca.markets/dashboard/");
});

it("refetches the equity history when the range changes", async () => {
  render(<PortfolioDialog open onOpenChange={() => {}} />);
  await screen.findByText("T7");

  await userEvent.click(screen.getByRole("button", { name: "1W" }));

  await waitFor(() => expect(getPortfolio).toHaveBeenCalledWith("1W"));
});
