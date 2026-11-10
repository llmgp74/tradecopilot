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
