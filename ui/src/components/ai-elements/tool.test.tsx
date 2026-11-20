import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it } from "vitest";
import { ToolCall, ToolGroup, aggregateState } from "./tool";

it("starts closed and opens the parameters with the camelCase name", async () => {
  render(
    <ToolCall
      label="Check SPY price"
      name="get_quote"
      state="output-available"
      input={{ ticker: "SPY", purpose: "Check entry" }}
      output="550.12"
    />,
  );
  expect(screen.queryByText("Parameters")).toBeNull();
  await userEvent.click(screen.getByText("Check SPY price"));
  expect(screen.getByText("Parameters")).toBeInTheDocument();
  expect(screen.getByText("getQuote")).toBeInTheDocument();
  expect(screen.getByText("550.12")).toBeInTheDocument();
});

it("hides the purpose argument from the parameters", async () => {
  const { container } = render(
    <ToolCall
      label="Check SPY price"
      name="get_quote"
      state="output-available"
      input={{ ticker: "SPY", purpose: "Check the entry" }}
      output="550.12"
    />,
  );
  await userEvent.click(screen.getByText("Check SPY price"));
  const text = container.textContent ?? "";
  expect(text).toContain("ticker");
  expect(text).not.toContain("purpose");
});

it("renders an object result as JSON", async () => {
  render(
    <ToolCall
      label="Read 10-Q.pdf"
      name="read_file"
      state="output-available"
      input={{ file_path: "/tmp/10-Q.pdf" }}
      output={{ content: "Revenue was 4.2 billion." }}
    />,
  );
  await userEvent.click(screen.getByText("Read 10-Q.pdf"));
  expect(screen.getByText(/Revenue was 4.2 billion/)).toBeInTheDocument();
});

it("shows an error instead of a result", async () => {
  render(
    <ToolCall
      label="Check SPY price"
      name="get_quote"
      state="output-error"
      input={{ ticker: "SPY" }}
      errorText="No price for SPY."
    />,
  );
  await userEvent.click(screen.getByText("Check SPY price"));
  expect(screen.getByText("No price for SPY.")).toBeInTheDocument();
  expect(screen.queryByText("Result")).toBeNull();
});

it("groups calls under one row and reveals each child", async () => {
  render(
    <ToolGroup label="Checked 3 prices" state="output-available">
      <ToolCall
        label="Check SPY price"
        name="get_quote"
        state="output-available"
        input={{ ticker: "SPY" }}
      />
      <ToolCall
        label="Check QQQ price"
        name="get_quote"
        state="output-available"
        input={{ ticker: "QQQ" }}
      />
      <ToolCall
        label="Check IWM price"
        name="get_quote"
        state="output-available"
        input={{ ticker: "IWM" }}
      />
    </ToolGroup>,
  );
  expect(screen.queryByText("Check QQQ price")).toBeNull();
  await userEvent.click(screen.getByText("Checked 3 prices"));
  expect(screen.getByText("Check QQQ price")).toBeInTheDocument();
});

it("aggregates child status", () => {
  expect(aggregateState(["output-available", "input-available"])).toBe(
    "input-available",
  );
  expect(aggregateState(["output-available", "output-error"])).toBe("output-error");
  expect(aggregateState(["output-denied", "output-available"])).toBe("output-error");
  expect(aggregateState(["output-available"])).toBe("output-available");
});
