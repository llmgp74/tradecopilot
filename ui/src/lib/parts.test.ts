import { expect, it } from "vitest";
import { normalizeMessages } from "./parts";

it("reads dynamic and static tool parts to the same view", () => {
  const [dynamicMessage] = normalizeMessages([
    {
      id: "a",
      role: "assistant",
      parts: [
        {
          type: "dynamic-tool",
          toolName: "get_quote",
          toolCallId: "c1",
          state: "output-available",
          input: { ticker: "NVDA" },
          output: "195",
        } as never,
      ],
    },
  ]);
  expect(dynamicMessage.parts[0]).toMatchObject({ name: "get_quote", output: "195" });

  const [staticMessage] = normalizeMessages([
    {
      id: "b",
      role: "assistant",
      parts: [
        {
          type: "tool-get_quote",
          toolCallId: "c2",
          state: "input-available",
          input: {},
        } as never,
      ],
    },
  ]);
  expect(staticMessage.parts[0]).toMatchObject({ name: "get_quote" });
});

it("normalizes nested and flat approval descriptors", () => {
  const [live] = normalizeMessages([
    {
      id: "a",
      role: "assistant",
      parts: [
        {
          type: "dynamic-tool",
          toolName: "execute_ticket",
          toolCallId: "c1",
          state: "approval-requested",
          approval: { id: "c1", descriptor: { ticket: { id: "t1" } } },
        } as never,
      ],
    },
  ]);
  expect(
    (live.parts[0] as { approval: { descriptor: { ticket: { id: string } } } }).approval
      .descriptor.ticket.id,
  ).toBe("t1");

  const [reloaded] = normalizeMessages([
    {
      id: "b",
      role: "assistant",
      parts: [
        {
          type: "tool-execute_ticket",
          toolCallId: "c2",
          state: "approval-requested",
          approval: { id: "c2", ticket: { id: "t2" }, rationale: "why" },
        } as never,
      ],
    },
  ]);
  const descriptor = (
    reloaded.parts[0] as { approval: { descriptor: { ticket: { id: string } } } }
  ).approval.descriptor;
  expect(descriptor).toMatchObject({ ticket: { id: "t2" }, rationale: "why" });
});

it("merges the later result into the first card and hides the duplicate", () => {
  const messages = normalizeMessages([
    {
      id: "a",
      role: "assistant",
      parts: [
        {
          type: "tool-execute_ticket",
          toolCallId: "c1",
          state: "approval-responded",
          approval: { id: "c1", approved: true },
        } as never,
      ],
    },
    {
      id: "b",
      role: "assistant",
      parts: [
        {
          type: "tool-execute_ticket",
          toolCallId: "c1",
          state: "output-available",
          output: { status: "filled" },
        } as never,
      ],
    },
  ]);
  expect((messages[0].parts[0] as { result: { output: unknown } }).result.output).toEqual(
    {
      status: "filled",
    },
  );
  expect((messages[1].parts[0] as { hidden: boolean }).hidden).toBe(true);
});

it("does not treat a re-emitted call as a result until it finishes", () => {
  const messages = normalizeMessages([
    {
      id: "a",
      role: "assistant",
      parts: [
        {
          type: "tool-execute_ticket",
          toolCallId: "c1",
          state: "approval-responded",
          approval: { id: "c1", approved: true },
        } as never,
      ],
    },
    {
      id: "b",
      role: "assistant",
      parts: [
        {
          type: "tool-execute_ticket",
          toolCallId: "c1",
          state: "input-available",
          input: { ticket_id: "t1" },
        } as never,
      ],
    },
  ]);
  expect((messages[0].parts[0] as { result?: unknown }).result).toBeUndefined();
  expect((messages[1].parts[0] as { hidden: boolean }).hidden).toBe(true);
});

it("keeps each reasoning segment's streaming state", () => {
  const [message] = normalizeMessages([
    {
      id: "a",
      role: "assistant",
      parts: [
        { type: "reasoning", text: "first", state: "done" } as never,
        { type: "reasoning", text: "second", state: "streaming" } as never,
      ],
    },
  ]);
  expect(message.parts).toMatchObject([
    { kind: "reasoning", streaming: false },
    { kind: "reasoning", streaming: true },
  ]);
});

it("reads todos from the last assistant message and ignores verification", () => {
  const messages = normalizeMessages([
    { id: "a", role: "assistant", parts: [{ type: "text", text: "hi" }] },
    {
      id: "b",
      role: "assistant",
      parts: [
        {
          type: "data-verification",
          data: { claims: [{ text: "x", verdict: "contradicted" }] },
        } as never,
        {
          type: "data-todos",
          data: { todos: [{ content: "p", status: "pending" }] },
        } as never,
      ],
    },
  ]);
  expect(messages[1].todos?.[0].content).toBe("p");
  expect(messages[1].parts).toEqual([]);
});
