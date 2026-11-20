import { useEffect, useMemo, useState } from "react";
import { useChat } from "@ai-sdk/react";
import {
  APICallError,
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
  PromptInputActionAddAttachments,
  PromptInputActionMenu,
  PromptInputActionMenuContent,
  PromptInputActionMenuTrigger,
  PromptInputBody,
  PromptInputFooter,
  PromptInputHeader,
  PromptInputSubmit,
  PromptInputTextarea,
  PromptInputTools,
  usePromptInputAttachments,
  type PromptInputMessage,
} from "@/components/ai-elements/prompt-input";
import { XIcon } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { apiUrl } from "@/lib/api-base";
import { patchSettings, type AppSettings } from "@/lib/api";
import { chatRequest } from "@/lib/chat-request";
import type { SettingsSection } from "@/lib/settings";
import { reasoningChoices } from "@/lib/reasoning";
import { ModelSelector } from "./model-selector";
import { ReasoningSelector } from "./reasoning-selector";
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
  /** Effective settings with the configured models. */
  settings: AppSettings;
  /** Opens the settings dialog on a section. */
  onOpenSettings: (section: SettingsSection) => void;
  /** Runs after a model switch so the shell can refresh the top bar. */
  onModelChanged?: () => void;
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
 * Shows the images waiting to be sent, each removable before submit.
 *
 * @returns The preview row, or nothing when no image is attached.
 */
function ComposerAttachments() {
  const attachments = usePromptInputAttachments();
  if (attachments.files.length === 0) {
    return null;
  }
  return (
    <PromptInputHeader className="flex flex-wrap gap-2 px-3 pt-3">
      {attachments.files.map((file) => (
        <div key={file.id} className="relative size-16 overflow-hidden rounded-md border">
          <img
            src={file.url}
            alt={file.filename ?? "Attached image"}
            className="size-full object-cover"
          />
          <button
            type="button"
            aria-label={`Remove ${file.filename ?? "image"}`}
            className="absolute right-1 top-1 rounded-full bg-background/80 p-0.5"
            onClick={() => attachments.remove(file.id)}
          >
            <XIcon className="size-3" />
          </button>
        </div>
      ))}
    </PromptInputHeader>
  );
}

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
  settings,
  onOpenSettings,
  onModelChanged,
  loadError,
}: ChatProps) {
  const [threadId, setThreadId] = useState<string | null>(initialThreadId);
  const [liveTodos, setLiveTodos] = useState<TodoItem[] | null>(null);
  // The reader's last reasoning toggle becomes the default for later blocks;
  // blocks already on screen keep whatever state they have.
  const [reasoningOpen, setReasoningOpen] = useState(false);
  const [selection, setSelection] = useState({
    provider: settings.model_provider,
    model: settings.model_id,
  });
  const [reasoning, setReasoning] = useState<string | null>(null);

  useEffect(() => {
    setSelection({
      provider: settings.model_provider,
      model: settings.model_id,
    });
    // The override belongs to the previous model's options.
    setReasoning(null);
  }, [settings.model_provider, settings.model_id]);

  const chooseModel = async (provider: string, model: string) => {
    try {
      const updated = await patchSettings({
        model_provider: provider,
        model_id: model,
      });
      setSelection({ provider: updated.model_provider, model: updated.model_id });
      setReasoning(null);
      onModelChanged?.();
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : "Could not switch model.");
    }
  };

  // Rebuilt when the thread id changes. useChat swaps transports without
  // resetting messages, so the turn that discovered the id keeps streaming.
  const transport = useMemo(
    () =>
      new DefaultChatTransport<UIMessage>({
        api: apiUrl("/api/chat"),
        prepareSendMessagesRequest: ({ messages }) =>
          chatRequest(messages as UIMessage[], threadId, reasoning),
      }),
    [threadId, reasoning],
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

  const selectedModel = settings.providers
    .find((item) => item.provider_id === selection.provider)
    ?.models.find((item) => item.id === selection.model);
  const reasoningOptions = reasoningChoices(selectedModel?.reasoning_options ?? []);

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
    const text = message.text.trim();
    if (!text && message.files.length === 0) {
      return;
    }
    // A blob URL means the browser could not read the file; sending it would
    // drop the image without telling anyone.
    if (message.files.some((file) => file.url?.startsWith("blob:"))) {
      toast.error("Could not read the attached image. Try again.");
      return;
    }
    setLiveTodos(null);
    sendMessage({ text, files: message.files });
  };

  return (
    <div className="flex h-full min-h-0 flex-col">
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
            <div className="flex flex-col gap-2 py-6">
              {display.map((message, position) =>
                message.role === "user" ? (
                  <Message
                    key={message.id}
                    from="user"
                    className={position > 0 ? "mt-4" : undefined}
                  >
                    <MessageContent className="rounded-2xl bg-muted px-3 py-2 text-[13px]">
                      {message.parts
                        .filter((part) => part.kind === "text")
                        .map((part) => (part.kind === "text" ? part.text : ""))
                        .join("")}
                    </MessageContent>
                  </Message>
                ) : (
                  <Message key={message.id} from="assistant">
                    <MessageContent className="w-full">
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
                        reasoningOpen={reasoningOpen}
                        onReasoningOpenChange={setReasoningOpen}
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
          {APICallError.isInstance(error) && error.statusCode === 503 ? (
            <Button variant="outline" size="sm" onClick={() => onOpenSettings("models")}>
              Open settings
            </Button>
          ) : null}
        </div>
      ) : null}

      <div className="mx-auto w-full max-w-[min(720px,100%-3rem)] px-0 pb-4">
        <PromptInput
          accept="image/png,image/jpeg,image/webp,image/gif"
          multiple
          maxFiles={4}
          maxFileSize={5 * 1024 * 1024}
          onError={(error) => toast.error(error.message)}
          onSubmit={handleSubmit}
        >
          <ComposerAttachments />
          <PromptInputBody>
            <PromptInputTextarea placeholder="Ask TradeCopilot..." />
          </PromptInputBody>
          <PromptInputFooter>
            <PromptInputTools>
              <PromptInputActionMenu>
                <PromptInputActionMenuTrigger aria-label="Add image" />
                <PromptInputActionMenuContent>
                  <PromptInputActionAddAttachments label="Add image" />
                </PromptInputActionMenuContent>
              </PromptInputActionMenu>
              <ModelSelector
                settings={settings}
                provider={selection.provider}
                modelId={selection.model}
                disabled={status === "streaming"}
                onChange={(provider, model) => void chooseModel(provider, model)}
                onManage={() => onOpenSettings("models")}
              />
              {reasoningOptions.length > 0 ? (
                <ReasoningSelector
                  choices={reasoningOptions}
                  value={reasoning}
                  disabled={status === "streaming"}
                  onChange={setReasoning}
                />
              ) : null}
            </PromptInputTools>
            <PromptInputSubmit status={status} onStop={stop} />
          </PromptInputFooter>
        </PromptInput>
      </div>
    </div>
  );
}
