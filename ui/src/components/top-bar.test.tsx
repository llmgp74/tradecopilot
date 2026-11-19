import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import type { ConnectionStatus } from "@/lib/connection";
import { TopBar } from "./top-bar";

function renderBar(status: ConnectionStatus, onOpenSettings = vi.fn()) {
  render(
    <TopBar
      title="NVDA earnings"
      onToggleRail={() => {}}
      railOpen
      status={status}
      onOpenSettings={onOpenSettings}
    />,
  );
  return onOpenSettings;
}

const unconfigured: ConnectionStatus = {
  broker: "unconfigured",
  environment: null,
  environmentVerified: false,
};

it("renders an unconfigured broker without an environment badge", () => {
  renderBar(unconfigured);

  expect(
    screen.getByRole("button", { name: "Broker not configured" }),
  ).toBeInTheDocument();
  expect(screen.queryByText("Paper")).not.toBeInTheDocument();
  expect(screen.queryByText("Live")).not.toBeInTheDocument();
});

it("renders saved keys with an unverified environment", () => {
  renderBar({ broker: "saved", environment: "paper", environmentVerified: false });

  expect(screen.getByRole("button", { name: "Broker saved" })).toBeInTheDocument();
  expect(screen.getByText("Paper")).toHaveAttribute("title", "Not verified");
});

it("renders a verified live connection", () => {
  renderBar({ broker: "connected", environment: "live", environmentVerified: true });

  expect(screen.getByRole("button", { name: "Alpaca" })).toBeInTheDocument();
  expect(screen.getByText("Live")).toBeInTheDocument();
});

it("renders an unreachable broker", () => {
  renderBar({ broker: "error", environment: "paper", environmentVerified: false });

  expect(screen.getByRole("button", { name: "Broker unreachable" })).toBeInTheDocument();
});

it("opens the broker section when clicked", async () => {
  const onOpenSettings = renderBar({
    broker: "connected",
    environment: "paper",
    environmentVerified: true,
  });

  await userEvent.click(screen.getByRole("button", { name: "Alpaca" }));

  expect(onOpenSettings).toHaveBeenCalledWith("broker");
});
