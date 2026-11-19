import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { ApprovalCard } from "./approval-card";
import type { ToolPartView } from "@/lib/parts";

const view: ToolPartView = {
  kind: "tool",
  toolCallId: "c1",
  name: "execute_ticket",
  state: "approval-requested",
  approval: {
    id: "c1",
    descriptor: {
      ticket: { id: "t1", legs: [{ ticker: "NVDA", side: "buy", qty: 8 }] },
      rationale: "Stay inside the cap.",
      portfolio_impact: {
        after_pct: { NVDA: 9.5 },
        net_notional: 1560,
        equity: 100000,
      },
    },
  },
};

it("approves the ticket", async () => {
  const onRespond = vi.fn();
  render(<ApprovalCard view={view} onRespond={onRespond} />);
  expect(screen.getByText("Ticket requires your approval")).toBeInTheDocument();
  expect(screen.getAllByText("NVDA").length).toBeGreaterThan(0);
  await userEvent.click(screen.getByRole("button", { name: /approve ticket/i }));
  expect(onRespond).toHaveBeenCalledWith("c1", true);
});

it("lays the legs out as a table with the weight change", () => {
  const ticketView: ToolPartView = {
    ...view,
    approval: {
      ...view.approval!,
      descriptor: {
        ticket: {
          id: "t1",
          legs: [
            { ticker: "NVDA", side: "buy", qty: 1 },
            { ticker: "LLY", side: "sell", qty: 2 },
          ],
        },
        portfolio_impact: {
          before_pct: { NVDA: 0.02, LLY: 0.14 },
          after_pct: { NVDA: 0.03, LLY: 0.11 },
        },
      },
    },
  };

  render(<ApprovalCard view={ticketView} onRespond={() => {}} />);

  expect(screen.getByText("Symbol")).toBeInTheDocument();
  expect(screen.getByText("Side")).toBeInTheDocument();
  expect(screen.getByText("Size")).toBeInTheDocument();
  expect(screen.getByText("Weight change")).toBeInTheDocument();
  expect(screen.getByText("2 shares")).toBeInTheDocument();
  expect(screen.getByText("0.02% to 0.03%")).toBeInTheDocument();
  expect(screen.getByText("0.14% to 0.11%")).toBeInTheDocument();
});

it("opens the full leg list in a dialog past ten rows", async () => {
  const legs = Array.from({ length: 12 }, (_, index) => ({
    ticker: `SYM${index}`,
    side: "buy" as const,
    qty: 1,
  }));
  const bigView: ToolPartView = {
    ...view,
    approval: {
      ...view.approval!,
      descriptor: { ticket: { id: "t1", legs } },
    },
  };

  render(<ApprovalCard view={bigView} onRespond={() => {}} />);

  expect(screen.getByText("SYM9")).toBeInTheDocument();
  expect(screen.queryByText("SYM10")).toBeNull();

  await userEvent.click(screen.getByRole("button", { name: /show all 12 legs/i }));

  expect(await screen.findByRole("dialog")).toBeInTheDocument();
  expect(screen.getByText("SYM10")).toBeInTheDocument();
  expect(screen.getByText("SYM11")).toBeInTheDocument();
});

it("asks for approval before cancelling orders", async () => {
  const onRespond = vi.fn();
  const cancelView: ToolPartView = {
    ...view,
    approval: {
      id: "c2",
      descriptor: {
        cancellation: {
          orders: [
            { order_id: "o1", ticker: "AAPL", side: "buy", qty: "1" },
            { order_id: "o2", ticker: "MSFT", side: "sell", qty: "2" },
          ],
        },
      },
    },
  };
  render(<ApprovalCard view={cancelView} onRespond={onRespond} />);

  expect(screen.getByText("Cancel open orders?")).toBeInTheDocument();
  expect(screen.getByText("AAPL")).toBeInTheDocument();
  expect(screen.getByText("MSFT")).toBeInTheDocument();

  await userEvent.click(screen.getByRole("button", { name: /approve cancellation/i }));

  expect(onRespond).toHaveBeenCalledWith("c2", true);
});

it("shows a rejected cancellation without actions", () => {
  const cancelView: ToolPartView = {
    ...view,
    approval: {
      id: "c2",
      approved: false,
      descriptor: {
        cancellation: { orders: [{ order_id: "o1", ticker: "AAPL", qty: "1" }] },
      },
    },
  };
  render(<ApprovalCard view={cancelView} onRespond={() => {}} />);

  expect(screen.getByText("Cancellation rejected")).toBeInTheDocument();
  expect(screen.queryByRole("button")).toBeNull();
});

it("rejects with a reason", async () => {
  const onRespond = vi.fn();
  render(<ApprovalCard view={view} onRespond={onRespond} />);
  await userEvent.click(screen.getByRole("button", { name: /reject/i }));
  await userEvent.type(screen.getByLabelText(/reason/i), "Too large");
  await userEvent.click(screen.getByRole("button", { name: /confirm rejection/i }));
  expect(onRespond).toHaveBeenCalledWith("c1", false, "Too large");
});

it("shows the execution result instead of buttons when present", () => {
  render(
    <ApprovalCard
      view={{ ...view, result: { output: "filled" } }}
      onRespond={() => {}}
    />,
  );
  expect(screen.getByText("Ticket executed")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /approve ticket/i })).toBeNull();
});

it("keeps the ticket and shows fills after execution", () => {
  const output = JSON.stringify({
    ticket_id: "t1",
    status: "filled",
    legs: [
      {
        ticker: "NVDA",
        side: "buy",
        qty: 8,
        status: "filled",
        fill_price: 190.5,
      },
    ],
  });

  render(
    <ApprovalCard
      view={{
        ...view,
        approval: { ...view.approval!, approved: true },
        result: { output },
      }}
      onRespond={() => {}}
    />,
  );

  expect(screen.getByText("Executed")).toBeInTheDocument();
  expect(screen.getAllByText("NVDA").length).toBeGreaterThan(0);
  expect(screen.getByText("Filled at $190.50")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /approve ticket/i })).toBeNull();
});

it("shows the reason after a rejection and disables the actions", () => {
  render(
    <ApprovalCard
      view={{
        ...view,
        approval: { ...view.approval!, approved: false, reason: "Too early" },
      }}
      onRespond={() => {}}
    />,
  );

  expect(screen.getByText("Ticket rejected")).toBeInTheDocument();
  expect(screen.getByText(/too early/i)).toBeInTheDocument();
  expect(screen.getAllByText("NVDA").length).toBeGreaterThan(0);
  expect(screen.queryByRole("button")).toBeNull();
});
