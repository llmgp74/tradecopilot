import { useMemo, useState } from "react";
import { useChat } from "@ai-sdk/react";
import {
  DefaultChatTransport,
  lastAssistantMessageIsCompleteWithApprovalResponses,
  type UIMessage,
} from "ai";
import {
  Conversation,
  ConversationContent,
  ConversationScrollButton,
} from "@/components/ai-elements/conversation";
import { Message, MessageContent } from "@/components/ai-elements/message";
import { AssistantParts } from "./assistant-parts";
import {
  PromptInput,
  PromptInputBody,
  PromptInputFooter,
  PromptInputSubmit,
  PromptInputTextarea,
  PromptInputTools,
  type PromptInputMessage,
} from "@/components/ai-elements/prompt-input";
import { Button } from "@/components/ui/button";
import { chatRequest } from "@/lib/chat-request";
import { normalizeMessages, type TodoItem } from "@/lib/parts";

/** Props supplied by the shell for one conversation epoch. */
export interface ChatProps {
  /** Conversation epoch. Changes remount the chat. */
  epoch: number;
  /** Thread to continue when restoring history. */
  initialThreadId: string | null;
  /** Messages rehydrated from thread detail. */
  initialMessages: UIMessage[];
  /** Reports the thread id created by the first turn. */
  onThreadStarted: (threadId: string) => void;
  /** Runs after a turn finishes so the rail can refresh. */
  onTurnFinished: () => void;
  /** True when no model is configured. */
  setupRequired: boolean;
  /** Opens the settings dialog. */
  onOpenSettings: () => void;
  /** Failure while restoring a stored thread. */
  loadError?: string | null;
}

const STARTER_PROMPTS = [
  "What moved the US market this week?",
  "Review my positions against my profile",
  "Is NVDA worth adding before earnings?",
  "Rebalance within my position cap",
];

/**
 * Renders the conversation, the composer, and the empty state.
 *
 * @param props - Chat session props supplied by the shell.
 * @returns The chat surface.
 */
export function Chat({
  initialThreadId,
  initialMessages,
  onThreadStarted,
  onTurnFinished,
  setupRequired,
  onOpenSettings,
  loadError,
}: ChatProps) {
  const [threadId, setThreadId] = useState<string | null>(initialThreadId);
  const [liveTodos, setLiveTodos] = useState<TodoItem[] | null>(null);

  // Rebuilt when the thread id changes. useChat swaps transports without
  // resetting messages, so the turn that discovered the id keeps streaming.
  const transport = useMemo(
    () =>
      new DefaultChatTransport<UIMessage>({
        api: "/api/chat",
        prepareSendMessagesRequest: ({ messages }) =>
          chatRequest(messages as UIMessage[], threadId),
      }),
    [threadId],
  );

  const { messages, sendMessage, status, stop, error, addToolApprovalResponse } = useChat(
    {
      messages: initialMessages,
      transport,
      onData: (part) => {
        const chunk = part as unknown as { type?: string; data?: unknown };
        if (chunk.type === "data-thread") {
          const id = (chunk.data as { thread_id?: string } | undefined)?.thread_id;
          if (id) {
            setThreadId(id);
            onThreadStarted(id);
          }
        }
        if (chunk.type === "data-todos") {
          const items = (chunk.data as { todos?: TodoItem[] } | undefined)?.todos;
          setLiveTodos(Array.isArray(items) ? items : null);
        }
      },
      onFinish: () => onTurnFinished(),
      sendAutomaticallyWhen: lastAssistantMessageIsCompleteWithApprovalResponses,
    },
  );

  const display = useMemo(() => normalizeMessages(messages), [messages]);

  const sendText = (text: string) => {
    const trimmed = text.trim();
    if (!trimmed) {
      return;
    }
    setLiveTodos(null);
    sendMessage({ text: trimmed });
  };

  const respond = (id: string, approved: boolean, reason?: string) => {
    setLiveTodos(null);
    addToolApprovalResponse({ id, approved, reason });
  };

  const handleSubmit = (message: PromptInputMessage) => {
    sendText(message.text);
  };

  return (
    <div className="flex h-full min-h-0 flex-col">
      {setupRequired ? (
        <div className="mx-auto mt-4 flex w-full max-w-[min(720px,100%-3rem)] items-center justify-between gap-3 rounded-lg border bg-muted px-4 py-3 text-sm">
          <span>Set a model to start.</span>
          <Button size="sm" onClick={onOpenSettings}>
            Open settings
          </Button>
        </div>
      ) : null}
      <Conversation className="min-h-0 flex-1">
        <ConversationContent className="mx-auto w-full max-w-[min(720px,100%-3rem)] px-0">
          {loadError ? (
            <div
              className="mx-auto mt-4 rounded-lg border px-4 py-3 text-sm"
              style={{
                color: "var(--negative)",
                background: "color-mix(in oklch, var(--negative) 8%, transparent)",
              }}
            >
              {loadError}
            </div>
          ) : null}
          {display.length === 0 ? (
            <div className="flex min-h-full flex-col items-center justify-center gap-6 py-16 text-center">
              <div className="space-y-1">
                <h1 className="text-xl font-semibold tracking-tight">
                  What would you like to know?
                </h1>
                <p className="text-sm text-muted-foreground">
                  Ask about a ticker, your positions, or the market.
                </p>
              </div>
              <div className="grid w-full max-w-110 grid-cols-1 gap-2 min-[720px]:grid-cols-2">
                {STARTER_PROMPTS.map((prompt) => (
                  <button
                    key={prompt}
                    type="button"
                    onClick={() => sendText(prompt)}
                    className="rounded-xl border bg-card px-3 py-3 text-left text-xs leading-snug text-foreground transition-colors hover:border-primary/40 hover:bg-accent"
                  >
                    {prompt}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="flex flex-col gap-6 py-6">
              {display.map((message) =>
                message.role === "user" ? (
                  <Message key={message.id} from="user">
                    <MessageContent className="rounded-2xl bg-muted px-3 py-2 text-[13px]">
                      {message.parts
                        .filter((part) => part.kind === "text")
                        .map((part) => (part.kind === "text" ? part.text : ""))
                        .join("")}
                    </MessageContent>
                  </Message>
                ) : (
                  <Message key={message.id} from="assistant">
                    <MessageContent>
                      <AssistantParts
                        message={message}
                        liveTodos={
                          message.id === display[display.length - 1]?.id
                            ? liveTodos
                            : null
                        }
                        isStreaming={
                          message.id === display[display.length - 1]?.id &&
                          status === "streaming"
                        }
                        onApproval={respond}
                      />
                    </MessageContent>
                  </Message>
                ),
              )}
            </div>
          )}
        </ConversationContent>
        <ConversationScrollButton />
      </Conversation>

      {error ? (
        <div
          className="mx-auto mb-2 flex w-full max-w-[min(720px,100%-3rem)] items-center gap-3 rounded-lg border px-4 py-2 text-xs"
          style={{ color: "var(--negative)" }}
        >
          <span className="min-w-0 flex-1">{error.message}</span>
          <Button variant="outline" size="sm" onClick={onOpenSettings}>
            Open settings
          </Button>
        </div>
      ) : null}

      <div className="mx-auto w-full max-w-[min(720px,100%-3rem)] px-0 pb-4">
        <PromptInput onSubmit={handleSubmit}>
          <PromptInputBody>
            <PromptInputTextarea placeholder="Ask TradeCopilot..." />
          </PromptInputBody>
          <PromptInputFooter>
            <PromptInputTools />
            <PromptInputSubmit status={status} onStop={stop} />
          </PromptInputFooter>
        </PromptInput>
      </div>
    </div>
  );
}
