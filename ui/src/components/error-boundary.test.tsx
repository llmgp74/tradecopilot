import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { ErrorBoundary } from "./error-boundary";

function Broken({ shouldThrow }: { shouldThrow: boolean }) {
  if (shouldThrow) {
    throw new Error("render failed");
  }
  return <p>Recovered</p>;
}

it("shows a fallback instead of a blank page and can retry", async () => {
  const spy = vi.spyOn(console, "error").mockImplementation(() => {});
  const { rerender } = render(
    <ErrorBoundary>
      <Broken shouldThrow />
    </ErrorBoundary>,
  );

  expect(screen.getByRole("alert")).toBeInTheDocument();

  rerender(
    <ErrorBoundary>
      <Broken shouldThrow={false} />
    </ErrorBoundary>,
  );
  await userEvent.click(screen.getByRole("button", { name: /try again/i }));

  expect(screen.getByText("Recovered")).toBeInTheDocument();
  spy.mockRestore();
});
