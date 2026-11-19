import type { UIMessage } from "ai";

/**
 * Builds the `/api/chat` body for one turn.
 *
 * The thread id is omitted for a new conversation, which lets the server
 * create one and return it in a `data-thread` part.
 *
 * @param messages - Full client history.
 * @param threadId - Current thread id, or null for a new thread.
 * @param reasoning - Per-turn reasoning override, or null to use the default.
 * @returns The request body.
 */
export function chatRequest(
  messages: UIMessage[],
  threadId: string | null,
  reasoning: string | null = null,
): {
  body: { messages: UIMessage[]; thread_id?: string; reasoning?: string };
} {
  return {
    body: {
      messages,
      ...(threadId === null ? {} : { thread_id: threadId }),
      ...(reasoning === null ? {} : { reasoning }),
    },
  };
}
