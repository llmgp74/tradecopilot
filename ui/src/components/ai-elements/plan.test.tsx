import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it } from "vitest";
import { Plan } from "./plan";

const todos = [
  { content: "Pull quotes", status: "completed" },
  { content: "Check the entry price", status: "in_progress" },
  { content: "Propose the ticket", status: "pending" },
] as const;

it("starts collapsed and names the running step", () => {
  render(<Plan todos={[...todos]} />);

  expect(screen.getByText("1 of 3 done")).toBeInTheDocument();
  expect(screen.getByText("Check the entry price")).toBeInTheDocument();
  expect(screen.queryByText("Pull quotes")).toBeNull();
});

it("reveals every step when expanded", async () => {
  render(<Plan todos={[...todos]} />);

  await userEvent.click(screen.getByText("Plan"));

  expect(screen.getByText("Pull quotes")).toBeInTheDocument();
  expect(screen.getByText("Check the entry price")).toBeInTheDocument();
  expect(screen.getByText("Propose the ticket")).toBeInTheDocument();
});
