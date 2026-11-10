import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { Rail } from "./rail";
import { ThemeProvider } from "@/theme-provider";

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
