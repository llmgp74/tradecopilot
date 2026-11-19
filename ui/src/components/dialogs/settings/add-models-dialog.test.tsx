import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { AddModelsDialog } from "./add-models-dialog";

const models = {
  "gpt-5": {
    name: "GPT-5",
    reasoning: true,
    reasoning_options: [{ type: "effort" as const, values: ["low", "high"] }],
    tool_call: true,
  },
  "gpt-5-mini": {
    name: "GPT-5 Mini",
    reasoning: true,
    reasoning_options: [],
    tool_call: true,
  },
  embed: {
    name: "Embed",
    reasoning: false,
    reasoning_options: [],
    tool_call: false,
  },
};

function renderDialog(onAdd = vi.fn()) {
  render(
    <AddModelsDialog
      open
      onOpenChange={() => {}}
      providerName="OpenAI"
      models={models}
      addedIds={[]}
      onAdd={onAdd}
    />,
  );
  return onAdd;
}

it("disables models without tool support", () => {
  renderDialog();

  expect(screen.getByRole("checkbox", { name: /embed/i })).toBeDisabled();
  expect(screen.getByText(/no tool support/i)).toBeInTheDocument();
});

it("filters by name and id", async () => {
  renderDialog();

  await userEvent.type(screen.getByLabelText(/search models/i), "mini");

  expect(screen.getByRole("checkbox", { name: /gpt-5 mini/i })).toBeInTheDocument();
  expect(screen.queryByRole("checkbox", { name: /^gpt-5$/i })).not.toBeInTheDocument();
});

it("adds the selected models with their capability metadata", async () => {
  const onAdd = renderDialog();

  await userEvent.click(screen.getByRole("checkbox", { name: /^gpt-5$/i }));
  await userEvent.click(screen.getByRole("checkbox", { name: /gpt-5 mini/i }));
  await userEvent.click(screen.getByRole("button", { name: "Add 2 models" }));

  expect(onAdd).toHaveBeenCalledWith([
    {
      id: "gpt-5",
      name: "GPT-5",
      tool_call: true,
      reasoning_options: [{ type: "effort", values: ["low", "high"] }],
    },
    {
      id: "gpt-5-mini",
      name: "GPT-5 Mini",
      tool_call: true,
      reasoning_options: [],
    },
  ]);
});

it("marks already-added models", () => {
  render(
    <AddModelsDialog
      open
      onOpenChange={() => {}}
      providerName="OpenAI"
      models={models}
      addedIds={["gpt-5"]}
      onAdd={vi.fn()}
    />,
  );

  expect(screen.getByRole("checkbox", { name: /^gpt-5$/i })).toBeDisabled();
  expect(screen.getByText(/already added/i)).toBeInTheDocument();
});
