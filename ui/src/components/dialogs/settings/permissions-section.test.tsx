import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";
import { patchSettings } from "@/lib/api";
import { baseSettings } from "@/test/fixtures";
import { PermissionsSection } from "./sections";

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...actual, patchSettings: vi.fn() };
});
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

beforeEach(() => {
  vi.mocked(patchSettings).mockResolvedValue({
    ...baseSettings,
    tool_permissions: { ...baseSettings.tool_permissions, execute: "auto" },
  });
});

it("shows one row per tool", () => {
  render(<PermissionsSection settings={baseSettings} onSaved={vi.fn()} />);
  for (const tool of ["execute", "write_file", "edit_file", "delete"]) {
    expect(screen.getByText(tool)).toBeInTheDocument();
  }
});

it("patches the full map when a policy changes", async () => {
  const onSaved = vi.fn();
  render(<PermissionsSection settings={baseSettings} onSaved={onSaved} />);

  await userEvent.click(screen.getByLabelText("execute approval"));
  await userEvent.click(screen.getByRole("option", { name: "Auto" }));

  await waitFor(() =>
    expect(patchSettings).toHaveBeenCalledWith({
      tool_permissions: {
        execute: "auto",
        write_file: "auto",
        edit_file: "auto",
        delete: "auto",
      },
    }),
  );
  expect(onSaved).toHaveBeenCalled();
});
