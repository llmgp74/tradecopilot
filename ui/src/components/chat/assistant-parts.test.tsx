import { render, screen, waitFor } from "@testing-library/react";
import { expect, it } from "vitest";
import { AssistantParts } from "./assistant-parts";
import type { DisplayMessage } from "@/lib/parts";

it("renders reasoning, a tool card, and the answer", () => {
  render(
    <AssistantParts
      onApproval={() => {}}
      message={{
        id: "a",
        role: "assistant",
        todos: null,
        parts: [
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
        ],
      }}
    />,
  );

  expect(screen.getByText("Check the current price")).toBeInTheDocument();
  expect(screen.getByText("NVDA is at 195.")).toBeInTheDocument();
});

it("renders a tool call before its input arrives", () => {
  render(
    <AssistantParts
      onApproval={() => {}}
      message={{
        id: "a",
        role: "assistant",
        todos: null,
        parts: [
          {
            kind: "tool",
            toolCallId: "c1",
            name: "get_quote",
            state: "input-streaming",
          },
        ],
      }}
    />,
  );

  expect(screen.getByText("Check the current price")).toBeInTheDocument();
});

it("collapses a tool card when the call finishes", async () => {
  const streamingTool: DisplayMessage = {
    id: "a",
    role: "assistant",
    todos: null,
    parts: [
      {
        kind: "tool",
        toolCallId: "c1",
        name: "get_quote",
        state: "input-available",
        input: { ticker: "NVDA" },
      },
    ],
  };
  const finishedTool: DisplayMessage = {
    ...streamingTool,
    parts: [
      {
        kind: "tool",
        toolCallId: "c1",
        name: "get_quote",
        state: "output-available",
        input: { ticker: "NVDA" },
        output: "195",
      },
    ],
  };

  const { rerender } = render(
    <AssistantParts message={streamingTool} isStreaming onApproval={() => {}} />,
  );
  expect(screen.getByText("Parameters")).toBeInTheDocument();

  rerender(
    <AssistantParts message={finishedTool} isStreaming={false} onApproval={() => {}} />,
  );

  await waitFor(() => expect(screen.queryByText("Parameters")).toBeNull());
});

it("collapses an open tool card when the turn ends without a result", async () => {
  const stuckTool: DisplayMessage = {
    id: "a",
    role: "assistant",
    todos: null,
    parts: [
      {
        kind: "tool",
        toolCallId: "c1",
        name: "verify_claims",
        state: "input-streaming",
        input: { claims: [] },
      },
    ],
  };

  const { rerender } = render(
    <AssistantParts message={stuckTool} isStreaming onApproval={() => {}} />,
  );
  expect(screen.getByText("Parameters")).toBeInTheDocument();

  rerender(
    <AssistantParts message={stuckTool} isStreaming={false} onApproval={() => {}} />,
  );

  await waitFor(() => expect(screen.queryByText("Parameters")).toBeNull());
});

it("does not render an approval card for an already executed ticket", () => {
  render(
    <AssistantParts
      onApproval={() => {}}
      message={{
        id: "a",
        role: "assistant",
        todos: null,
        parts: [
          {
            kind: "tool",
            toolCallId: "c1",
            name: "execute_ticket",
            state: "output-available",
            output: "filled",
          },
        ],
      }}
    />,
  );

  expect(screen.queryByText("Ticket requires your approval")).toBeNull();
  expect(screen.queryByRole("button", { name: /approve ticket/i })).toBeNull();
});
