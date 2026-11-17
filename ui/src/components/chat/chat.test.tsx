import { fireEvent, render, screen, waitFor } from "@testing-library/react";
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

it("sends an image pasted into the composer", async () => {
  Object.assign(URL, {
    createObjectURL: vi.fn(() => "blob:chart"),
    revokeObjectURL: vi.fn(),
  });
  // jsdom's FileReader rejects the Blob returned by the fetch mock, so the
  // conversion is faked with the same data URL shape a browser produces.
  vi.stubGlobal(
    "FileReader",
    class {
      result: string | null = null;
      onloadend: (() => void) | null = null;
      onerror: (() => void) | null = null;
      readAsDataURL(blob: Blob) {
        this.result = `data:${blob.type || "image/png"};base64,AA==`;
        this.onloadend?.();
      }
    },
  );
  const fetchMock = vi.fn().mockResolvedValue(sseResponse([{ type: "finish" }]));
  vi.stubGlobal("fetch", fetchMock);

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

  const file = new File([new Uint8Array([1, 2, 3])], "chart.png", {
    type: "image/png",
  });
  fireEvent.paste(screen.getByPlaceholderText(/ask tradecopilot/i), {
    clipboardData: { items: [{ kind: "file", getAsFile: () => file }] },
  });
  expect(await screen.findByAltText("chart.png")).toBeInTheDocument();

  await userEvent.type(
    screen.getByPlaceholderText(/ask tradecopilot/i),
    "See this{Enter}",
  );

  await waitFor(() => {
    const chatCall = fetchMock.mock.calls.find((call) =>
      String(call[0]).includes("/api/chat"),
    );
    expect(chatCall).toBeDefined();
    const body = JSON.parse((chatCall?.[1] as RequestInit).body as string) as {
      messages: { parts: { type: string; mediaType?: string }[] }[];
    };
    const parts = body.messages[0].parts;
    expect(parts.some((part) => part.type === "file")).toBe(true);
  });
});

it("opens the file picker from the plus menu", async () => {
  const click = vi
    .spyOn(HTMLInputElement.prototype, "click")
    .mockImplementation(() => {});

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

  await userEvent.click(screen.getByRole("button", { name: "Add image" }));
  const item = await screen.findByRole("menuitem", { name: /add image/i });
  await userEvent.click(item);

  expect(click).toHaveBeenCalled();
});
