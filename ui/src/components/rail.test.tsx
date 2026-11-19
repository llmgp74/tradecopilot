import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import { Rail } from "./rail";
import { ThemeProvider } from "@/theme-provider";

afterEach(() => vi.restoreAllMocks());

function renderRailFor(userAgent: string) {
  vi.spyOn(navigator, "userAgent", "get").mockReturnValue(userAgent);
  render(
    <ThemeProvider>
      <Rail
        open
        threads={[]}
        activeThreadId={null}
        onToggle={() => {}}
        onNewChat={() => {}}
        onOpenThread={() => {}}
        onOpenDialog={() => {}}
      />
    </ThemeProvider>,
  );
}

it("lists threads and opens destinations", async () => {
  const onOpenDialog = vi.fn();
  render(
    <ThemeProvider>
      <Rail
        open
        threads={[{ thread_id: "t1", title: "NVDA", created_at: "", updated_at: "" }]}
        activeThreadId={null}
        onToggle={() => {}}
        onNewChat={() => {}}
        onOpenThread={() => {}}
        onOpenDialog={onOpenDialog}
      />
    </ThemeProvider>,
  );

  expect(screen.getByText("NVDA")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Portfolio" }));
  expect(onOpenDialog).toHaveBeenCalledWith("portfolio");
});

it("shows the Command shortcut on macOS", () => {
  renderRailFor("Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0)");

  expect(
    screen.getByRole("button", { name: /new chat, command \+ n/i }),
  ).toBeInTheDocument();
});

it("shows the Ctrl shortcut on Windows", () => {
  renderRailFor("Mozilla/5.0 (Windows NT 10.0; Win64; x64)");

  expect(
    screen.getByRole("button", { name: /new chat, ctrl \+ n/i }),
  ).toBeInTheDocument();
});
