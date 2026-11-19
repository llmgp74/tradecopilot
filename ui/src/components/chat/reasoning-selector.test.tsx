import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { ReasoningSelector } from "./reasoning-selector";

const choices = [
  { value: "off", label: "Off" },
  { value: "low", label: "Low" },
  { value: "high", label: "High" },
];

async function openMenu(name: RegExp) {
  screen.getByRole("button", { name }).focus();
  await userEvent.keyboard("{ArrowDown}");
}

it("reads Default while the value is inherited", () => {
  render(
    <ReasoningSelector
      choices={choices}
      value={null}
      disabled={false}
      onChange={() => {}}
    />,
  );

  expect(screen.getByRole("button", { name: /^default$/i })).toBeInTheDocument();
});

it("shows the chosen level", async () => {
  const onChange = vi.fn();
  render(
    <ReasoningSelector
      choices={choices}
      value={null}
      disabled={false}
      onChange={onChange}
    />,
  );

  await openMenu(/^default$/i);
  await userEvent.click(screen.getByRole("menuitemradio", { name: "High" }));

  expect(onChange).toHaveBeenCalledWith("high");
});

it("returns to the default from the menu", async () => {
  const onChange = vi.fn();
  render(
    <ReasoningSelector
      choices={choices}
      value="high"
      disabled={false}
      onChange={onChange}
    />,
  );

  await openMenu(/^high$/i);
  await userEvent.click(screen.getByRole("menuitemradio", { name: "Default" }));

  expect(onChange).toHaveBeenCalledWith(null);
});
