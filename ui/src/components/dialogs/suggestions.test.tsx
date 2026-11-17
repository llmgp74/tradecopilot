import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";
import { SuggestionCards } from "./profile";
import type { Suggestion } from "@/lib/api";
import { baseProfile } from "@/test/fixtures";

const { patchProfile, dismissSuggestion } = vi.hoisted(() => ({
  patchProfile: vi.fn(),
  dismissSuggestion: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  getProfile: vi.fn(),
  patchProfile,
  dismissSuggestion,
}));

const suggestion: Suggestion = {
  key: "cap_8",
  kind: "cap",
  title: "Lower the position cap to 8%",
  rationale: "2 recent rejections.",
  patch: { position_cap_pct: 8 },
  decision_ids: ["a", "b"],
};

beforeEach(() => {
  patchProfile.mockReset();
  dismissSuggestion.mockReset();
});

it("accepts a hard suggestion after confirmation", async () => {
  const onChanged = vi.fn();
  patchProfile.mockResolvedValue({ ...baseProfile, position_cap_pct: 8 });
  render(<SuggestionCards suggestions={[suggestion]} onChanged={onChanged} />);

  await userEvent.click(screen.getByRole("button", { name: "Accept" }));
  expect(screen.getByText("Change a hard constraint?")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Save changes" }));

  await waitFor(() => expect(patchProfile).toHaveBeenCalledWith({ position_cap_pct: 8 }));
  expect(onChanged).toHaveBeenCalled();
});

it("dismisses a suggestion", async () => {
  const onChanged = vi.fn();
  dismissSuggestion.mockResolvedValue(undefined);
  render(<SuggestionCards suggestions={[suggestion]} onChanged={onChanged} />);

  await userEvent.click(screen.getByRole("button", { name: "Dismiss" }));

  await waitFor(() => expect(dismissSuggestion).toHaveBeenCalledWith("cap_8"));
  expect(onChanged).toHaveBeenCalled();
});

it("accepts a horizon suggestion without confirmation", async () => {
  patchProfile.mockResolvedValue({ ...baseProfile, horizon: "months" });
  render(
    <SuggestionCards
      suggestions={[
        {
          ...suggestion,
          key: "horizon_months",
          kind: "horizon",
          title: "Lengthen the horizon to months",
          patch: { horizon: "months" },
        },
      ]}
      onChanged={() => {}}
    />,
  );

  await userEvent.click(screen.getByRole("button", { name: "Accept" }));

  await waitFor(() => expect(patchProfile).toHaveBeenCalledWith({ horizon: "months" }));
  expect(screen.queryByText("Change a hard constraint?")).toBeNull();
});
