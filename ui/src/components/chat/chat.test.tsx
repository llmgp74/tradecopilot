import type { UIMessage } from "ai";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { Chat } from "./chat";
import { sseResponse } from "@/test/sse";
import { baseSettings } from "@/test/fixtures";

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
      settings={baseSettings}
      onOpenSettings={() => {}}
    />,
  );

  await userEvent.type(screen.getByPlaceholderText(/ask tradecopilot/i), "Hello{Enter}");

  expect(await screen.findByText("Hello")).toBeInTheDocument();
  expect(await screen.findByText("Hi there")).toBeInTheDocument();
  await waitFor(() => expect(onThreadStarted).toHaveBeenCalledWith("abc"));
});

it("offers a working stop control while a turn streams", async () => {
  let signal: AbortSignal | undefined;
  vi.stubGlobal(
    "fetch",
    vi.fn((_url: string, init?: RequestInit) => {
      signal = init?.signal ?? undefined;
      const encoder = new TextEncoder();
      return Promise.resolve(
        new Response(
          new ReadableStream({
            start(controller) {
              controller.enqueue(
                encoder.encode('data: {"type":"start","messageId":"m1"}\n\n'),
              );
              controller.enqueue(
                encoder.encode('data: {"type":"text-start","id":"t1"}\n\n'),
              );
              controller.enqueue(
                encoder.encode(
                  'data: {"type":"text-delta","id":"t1","delta":"Partial"}\n\n',
                ),
              );
            },
          }),
          {
            status: 200,
            headers: {
              "Content-Type": "text/event-stream",
              "x-vercel-ai-ui-message-stream": "v1",
            },
          },
        ),
      );
    }),
  );

  render(
    <Chat
      epoch={0}
      initialThreadId={null}
      initialMessages={[]}
      onThreadStarted={() => {}}
      onTurnFinished={() => {}}
      settings={baseSettings}
      onOpenSettings={() => {}}
    />,
  );

  await userEvent.type(screen.getByPlaceholderText(/ask tradecopilot/i), "Hello{Enter}");

  const stop = await screen.findByRole("button", { name: "Stop" });
  expect(stop).toBeEnabled();

  await userEvent.click(stop);

  await waitFor(() => expect(signal?.aborted).toBe(true));
});

it("shows a stop icon while waiting for the first token", async () => {
  let signal: AbortSignal | undefined;
  vi.stubGlobal(
    "fetch",
    vi.fn((_url: string, init?: RequestInit) => {
      signal = init?.signal ?? undefined;
      return new Promise<Response>(() => {});
    }),
  );

  render(
    <Chat
      epoch={0}
      initialThreadId={null}
      initialMessages={[]}
      onThreadStarted={() => {}}
      onTurnFinished={() => {}}
      settings={baseSettings}
      onOpenSettings={() => {}}
    />,
  );

  await userEvent.type(screen.getByPlaceholderText(/ask tradecopilot/i), "Hello{Enter}");

  const stop = await screen.findByRole("button", { name: "Stop" });
  expect(stop.querySelector("svg.lucide-square")).not.toBeNull();

  await userEvent.click(stop);

  await waitFor(() => expect(signal?.aborted).toBe(true));
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
      settings={baseSettings}
      onOpenSettings={() => {}}
    />,
  );

  await userEvent.type(screen.getByPlaceholderText(/ask tradecopilot/i), "Hello{Enter}");

  expect(await screen.findByText("Pull latest filings")).toBeInTheDocument();
});

it("pins a persisted plan above the composer", () => {
  const messages = [
    { id: "u1", role: "user", parts: [{ type: "text", text: "Rebalance" }] },
    {
      id: "a1",
      role: "assistant",
      parts: [{ type: "text", text: "First step." }],
    },
    {
      id: "a2",
      role: "assistant",
      parts: [
        { type: "text", text: "Final answer." },
        {
          type: "data-todos",
          data: {
            type: "todos",
            todos: [{ content: "Pull quotes", status: "completed" }],
          },
        },
      ],
    },
  ] as UIMessage[];

  render(
    <Chat
      epoch={0}
      initialThreadId={null}
      initialMessages={messages}
      onThreadStarted={() => {}}
      onTurnFinished={() => {}}
      settings={baseSettings}
      onOpenSettings={() => {}}
    />,
  );

  const plan = screen.getByText("Plan");
  const composer = screen.getByPlaceholderText(/ask tradecopilot/i);
  expect(
    plan.compareDocumentPosition(composer) & Node.DOCUMENT_POSITION_FOLLOWING,
  ).toBeTruthy();
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
      settings={baseSettings}
      onOpenSettings={() => {}}
    />,
  );

  await userEvent.type(screen.getByPlaceholderText(/ask tradecopilot/i), "Hello{Enter}");

  expect(
    await screen.findByRole("button", { name: /open settings/i }),
  ).toBeInTheDocument();
});

it("shows a run error without the settings escape hatch", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      sseResponse([
        { type: "start", messageId: "m1" },
        {
          type: "error",
          errorText: "At key 'pending_ticket': Can receive only one value per step.",
        },
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
      settings={baseSettings}
      onOpenSettings={() => {}}
    />,
  );

  await userEvent.type(screen.getByPlaceholderText(/ask tradecopilot/i), "Hello{Enter}");

  expect(await screen.findByText(/can receive only one value/i)).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /open settings/i })).toBeNull();
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
      settings={baseSettings}
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
      settings={baseSettings}
      onOpenSettings={() => {}}
    />,
  );

  await userEvent.click(screen.getByRole("button", { name: "Add image" }));
  const item = await screen.findByRole("menuitem", { name: /add image/i });
  await userEvent.click(item);

  expect(click).toHaveBeenCalled();
});

it("switches the model through settings", async () => {
  const onModelChanged = vi.fn();
  const settings = {
    ...baseSettings,
    providers: [
      baseSettings.providers[0],
      {
        provider_id: "openai",
        api_key: "sk",
        base_url: "",
        npm: "@ai-sdk/openai",
        models: [{ id: "gpt-5", name: "GPT-5", tool_call: true, reasoning_options: [] }],
        updated_at: "2026-11-01T00:00:00Z",
      },
    ],
  };
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    if (String(input).includes("/api/settings") && init?.method === "PATCH") {
      return new Response(
        JSON.stringify({ ...settings, model_provider: "openai", model_id: "gpt-5" }),
        { status: 200 },
      );
    }
    return sseResponse([]);
  });
  vi.stubGlobal("fetch", fetchMock);

  render(
    <Chat
      epoch={0}
      initialThreadId={null}
      initialMessages={[]}
      onThreadStarted={() => {}}
      onTurnFinished={() => {}}
      settings={settings}
      onOpenSettings={() => {}}
      onModelChanged={onModelChanged}
    />,
  );

  const trigger = screen.getByRole("button", { name: /deepseek v4.1 flash/i });
  trigger.focus();
  await userEvent.keyboard("{ArrowDown}");
  await userEvent.click(screen.getByRole("menuitemradio", { name: /^gpt-5$/i }));

  await waitFor(() =>
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/api/settings"),
      expect.objectContaining({ method: "PATCH" }),
    ),
  );
  expect(await screen.findByRole("button", { name: /^gpt-5$/i })).toBeInTheDocument();
});

it("sends the temporary reasoning override with the turn", async () => {
  let captured = "";
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    if (String(input).includes("/api/chat")) {
      captured = String(init?.body ?? "");
      return sseResponse([
        { type: "start", messageId: "m1" },
        { type: "text-start", id: "t1" },
        { type: "text-delta", id: "t1", delta: "ok" },
        { type: "text-end", id: "t1" },
        { type: "finish" },
      ]);
    }
    return sseResponse([]);
  });
  vi.stubGlobal("fetch", fetchMock);

  render(
    <Chat
      epoch={0}
      initialThreadId={null}
      initialMessages={[]}
      onThreadStarted={() => {}}
      onTurnFinished={() => {}}
      settings={baseSettings}
      onOpenSettings={() => {}}
    />,
  );

  const trigger = screen.getByRole("button", { name: /^default$/i });
  trigger.focus();
  await userEvent.keyboard("{ArrowDown}");
  await userEvent.click(screen.getByRole("menuitemradio", { name: "High" }));
  await userEvent.type(screen.getByPlaceholderText(/ask tradecopilot/i), "Hello{Enter}");

  await waitFor(() => expect(captured).toContain('"reasoning":"high"'));
  expect(screen.getByRole("button", { name: /^high$/i })).toBeInTheDocument();
});

it("resets the reasoning override when the selected model changes", async () => {
  const provider = baseSettings.providers[0];
  const settings = {
    ...baseSettings,
    providers: [
      {
        ...provider,
        models: [
          provider.models[0],
          {
            id: "deepseek-v4-pro",
            name: "DeepSeek V4 Pro",
            tool_call: true,
            reasoning_options: [{ type: "toggle" as const }],
          },
        ],
      },
    ],
  };
  const { rerender } = render(
    <Chat
      epoch={0}
      initialThreadId={null}
      initialMessages={[]}
      onThreadStarted={() => {}}
      onTurnFinished={() => {}}
      settings={settings}
      onOpenSettings={() => {}}
    />,
  );

  const trigger = screen.getByRole("button", { name: /^default$/i });
  trigger.focus();
  await userEvent.keyboard("{ArrowDown}");
  await userEvent.click(screen.getByRole("menuitemradio", { name: "High" }));
  expect(screen.getByRole("button", { name: /^high$/i })).toBeInTheDocument();

  rerender(
    <Chat
      epoch={0}
      initialThreadId={null}
      initialMessages={[]}
      onThreadStarted={() => {}}
      onTurnFinished={() => {}}
      settings={{ ...settings, model_id: "deepseek-v4-pro" }}
      onOpenSettings={() => {}}
    />,
  );

  expect(await screen.findByRole("button", { name: /^default$/i })).toBeInTheDocument();
});
