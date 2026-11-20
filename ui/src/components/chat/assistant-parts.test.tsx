import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it } from "vitest";
import { AssistantParts } from "./assistant-parts";
import type { DisplayMessage } from "@/lib/parts";

function toolMessage(parts: DisplayMessage["parts"]): DisplayMessage {
  return { id: "a", role: "assistant", todos: null, parts };
}

it("renders reasoning, a tool card, and the answer", () => {
  render(
    <AssistantParts
      onApproval={() => {}}
      message={toolMessage([
        { kind: "reasoning", text: "Thinking about it", streaming: false },
        {
          kind: "tool",
          toolCallId: "c1",
          name: "get_quote",
          state: "output-available",
          input: { ticker: "NVDA" },
          output: "195",
        },
        { kind: "text", text: "NVDA is at 195." },
      ])}
    />,
  );

  expect(screen.getByText("Check NVDA price")).toBeInTheDocument();
  expect(screen.getByText("NVDA is at 195.")).toBeInTheDocument();
});

it("labels a tool row from its arguments and keeps it closed", () => {
  render(
    <AssistantParts
      onApproval={() => {}}
      message={toolMessage([
        {
          kind: "tool",
          toolCallId: "c1",
          name: "get_quote",
          state: "output-available",
          input: { ticker: "NVDA" },
          output: "195",
        },
      ])}
    />,
  );
  expect(screen.getByText("Check NVDA price")).toBeInTheDocument();
  expect(screen.queryByText("Parameters")).toBeNull();
});

it("renders a tool row before its input arrives", () => {
  render(
    <AssistantParts
      onApproval={() => {}}
      message={toolMessage([
        {
          kind: "tool",
          toolCallId: "c1",
          name: "get_quote",
          state: "input-streaming",
        },
      ])}
    />,
  );

  expect(screen.getByText("Check price")).toBeInTheDocument();
});

it("uses the model purpose for the row", () => {
  render(
    <AssistantParts
      onApproval={() => {}}
      message={toolMessage([
        {
          kind: "tool",
          toolCallId: "c1",
          name: "get_quote",
          state: "output-available",
          input: { ticker: "NVDA", purpose: "Check the entry price" },
          output: "195",
        },
      ])}
    />,
  );

  expect(screen.getByText("Check the entry price")).toBeInTheDocument();
});

it("keeps a row open when the call finishes", async () => {
  const streaming = toolMessage([
    {
      kind: "tool",
      toolCallId: "c1",
      name: "get_quote",
      state: "input-available",
      input: { ticker: "NVDA" },
    },
  ]);
  const finished = toolMessage([
    {
      kind: "tool",
      toolCallId: "c1",
      name: "get_quote",
      state: "output-available",
      input: { ticker: "NVDA" },
      output: "195",
    },
  ]);

  const { rerender } = render(
    <AssistantParts message={streaming} isStreaming onApproval={() => {}} />,
  );
  await userEvent.click(screen.getByText("Check NVDA price"));
  expect(screen.getByText("Parameters")).toBeInTheDocument();

  rerender(
    <AssistantParts message={finished} isStreaming={false} onApproval={() => {}} />,
  );

  expect(screen.getByText("Parameters")).toBeInTheDocument();
});

it("keeps an opened row open when a second call joins it", async () => {
  const single = toolMessage([
    {
      kind: "tool",
      toolCallId: "c1",
      name: "get_quote",
      state: "output-available",
      input: { ticker: "NVDA" },
    },
  ]);
  const pair = toolMessage([
    {
      kind: "tool",
      toolCallId: "c1",
      name: "get_quote",
      state: "output-available",
      input: { ticker: "NVDA" },
    },
    {
      kind: "tool",
      toolCallId: "c2",
      name: "get_quote",
      state: "input-available",
      input: { ticker: "AMD" },
    },
  ]);

  const { rerender } = render(
    <AssistantParts message={single} isStreaming onApproval={() => {}} />,
  );
  await userEvent.click(screen.getByText("Check NVDA price"));

  rerender(<AssistantParts message={pair} isStreaming onApproval={() => {}} />);

  expect(screen.getByText("Check AMD price")).toBeInTheDocument();
});

it("groups consecutive calls of the same tool", async () => {
  render(
    <AssistantParts
      onApproval={() => {}}
      message={toolMessage([
        {
          kind: "tool",
          toolCallId: "c1",
          name: "get_quote",
          state: "output-available",
          input: { ticker: "SPY" },
        },
        {
          kind: "tool",
          toolCallId: "c2",
          name: "get_quote",
          state: "output-available",
          input: { ticker: "QQQ" },
        },
        {
          kind: "tool",
          toolCallId: "c3",
          name: "get_quote",
          state: "output-available",
          input: { ticker: "IWM" },
        },
      ])}
    />,
  );

  expect(screen.queryByText("Check QQQ price")).toBeNull();
  await userEvent.click(screen.getByText("Checked 3 prices: SPY, QQQ, IWM"));
  expect(screen.getByText("Check QQQ price")).toBeInTheDocument();
});

it("keeps a single call and a different tool as separate rows", () => {
  render(
    <AssistantParts
      onApproval={() => {}}
      message={toolMessage([
        {
          kind: "tool",
          toolCallId: "c1",
          name: "get_quote",
          state: "output-available",
          input: { ticker: "SPY" },
        },
        {
          kind: "tool",
          toolCallId: "c2",
          name: "get_quote",
          state: "output-available",
          input: { ticker: "QQQ" },
        },
        {
          kind: "tool",
          toolCallId: "c3",
          name: "get_news",
          state: "output-available",
          input: { ticker: "SPY" },
        },
      ])}
    />,
  );

  expect(screen.getByText("Checked 2 prices: SPY, QQQ")).toBeInTheDocument();
  expect(screen.getByText("Read SPY news")).toBeInTheDocument();
});

it("renders an awaiting ticket as an approval card, not a group row", () => {
  render(
    <AssistantParts
      onApproval={() => {}}
      message={toolMessage([
        {
          kind: "tool",
          toolCallId: "c1",
          name: "execute_ticket",
          state: "approval-requested",
          input: { ticket_id: "t1", purpose: "Place the ticket" },
          approval: { id: "a1", descriptor: null },
        },
      ])}
    />,
  );

  expect(screen.getByText("Ticket requires your approval")).toBeInTheDocument();
  expect(screen.queryByText("Place the ticket")).toBeNull();
});

it("does not render an approval card for an already executed ticket", () => {
  render(
    <AssistantParts
      onApproval={() => {}}
      message={toolMessage([
        {
          kind: "tool",
          toolCallId: "c1",
          name: "execute_ticket",
          state: "output-available",
          output: "filled",
        },
      ])}
    />,
  );

  expect(screen.queryByText("Ticket requires your approval")).toBeNull();
  expect(screen.queryByRole("button", { name: /approve ticket/i })).toBeNull();
});

it("reveals the reasoning text when the trigger is clicked", async () => {
  render(
    <AssistantParts
      onApproval={() => {}}
      message={toolMessage([
        { kind: "reasoning", text: "Checking the price first", streaming: false },
      ])}
    />,
  );

  await userEvent.click(screen.getByText(/thought for a few seconds/i));

  expect(await screen.findByText("Checking the price first")).toBeInTheDocument();
});
