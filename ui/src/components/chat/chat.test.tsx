import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { Chat } from "./chat";
import { sseResponse } from "@/test/sse";

it("streams an answer and reports the new thread id", async () => {
  vi.stubGlobal(
    "fetch",
    vi
      .fn()
      .mockResolvedValue(
        sseResponse([
          { type: "start", messageId: "m1" },
          { type: "data-thread", data: { thread_id: "abc" }, transient: true },
          { type: "text-start", id: "t1" },
          { type: "text-delta", id: "t1", delta: "Hi there" },
          { type: "text-end", id: "t1" },
          { type: "finish" },
        ]),
      ),
  );
  const onThreadStarted = vi.fn();

  render(
    <Chat
      epoch={0}
      initialThreadId={null}
      initialMessages={[]}
      onThreadStarted={onThreadStarted}
      onTurnFinished={() => {}}
      setupRequired={false}
      onOpenSettings={() => {}}
    />,
  );

  await userEvent.type(screen.getByPlaceholderText(/ask tradecopilot/i), "Hello{Enter}");

  expect(await screen.findByText("Hello")).toBeInTheDocument();
  expect(await screen.findByText("Hi there")).toBeInTheDocument();
  await waitFor(() => expect(onThreadStarted).toHaveBeenCalledWith("abc"));
});

it("renders the live plan from a transient todos part", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      sseResponse([
        { type: "start", messageId: "m1" },
        {
          type: "data-todos",
          data: {
            type: "todos",
            todos: [{ content: "Pull latest filings", status: "pending" }],
          },
        },
        { type: "finish" },
      ]),
    ),
  );

  render(
    <Chat
      epoch={0}
      initialThreadId={null}
      initialMessages={[]}
      onThreadStarted={() => {}}
      onTurnFinished={() => {}}
      setupRequired={false}
      onOpenSettings={() => {}}
    />,
  );

  await userEvent.type(screen.getByPlaceholderText(/ask tradecopilot/i), "Hello{Enter}");

  expect(await screen.findByText("Pull latest filings")).toBeInTheDocument();
});

it("shows a request error with the settings escape hatch", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: "AGENT_MODEL is not set." }), {
        status: 503,
        headers: { "Content-Type": "application/json" },
      }),
    ),
  );

  render(
    <Chat
      epoch={0}
      initialThreadId={null}
      initialMessages={[]}
      onThreadStarted={() => {}}
      onTurnFinished={() => {}}
      setupRequired={false}
      onOpenSettings={() => {}}
    />,
  );

  await userEvent.type(screen.getByPlaceholderText(/ask tradecopilot/i), "Hello{Enter}");

  expect(
    await screen.findByRole("button", { name: /open settings/i }),
  ).toBeInTheDocument();
});
