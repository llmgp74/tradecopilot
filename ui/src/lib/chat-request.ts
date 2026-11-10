import type { UIMessage } from "ai";

/**
 * Builds the `/api/chat` body for one turn.
 *
 * The thread id is omitted for a new conversation, which lets the server
 * create one and return it in a `data-thread` part.
 *
 * @param messages - Full client history.
 * @param threadId - Current thread id, or null for a new thread.
 * @returns The request body.
 */
export function chatRequest(
  messages: UIMessage[],
  threadId: string | null,
): { body: { messages: UIMessage[]; thread_id?: string } } {
  return {
    body: threadId === null ? { messages } : { messages, thread_id: threadId },
  };
}
