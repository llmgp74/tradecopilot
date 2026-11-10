import type { UIMessage } from "ai";
import type { ThreadSummary } from "./api";

/** Conversation session state owned by the shell. */
export interface ConversationState {
  /** Changes only when a different conversation starts. Keys `useChat`. */
  epoch: number;
  /** Active thread id, or null before the first turn. */
  threadId: string | null;
  /** Messages used to seed `useChat` when a thread opens. */
  initialMessages: UIMessage[];
}

/** Actions accepted by {@link conversationReducer}. */
export type ConversationAction =
  | { type: "new" }
  | { type: "open"; threadId: string; messages: UIMessage[] }
  | { type: "started"; threadId: string };

/** Starting state for a fresh conversation. */
export const initialConversationState: ConversationState = {
  epoch: 0,
  threadId: null,
  initialMessages: [],
};

/**
 * Applies a conversation transition.
 *
 * A mid-stream thread id only records the id; it never changes the epoch, so
 * the first answer is not discarded. Only new or opened conversations reset
 * the chat instance.
 *
 * @param state - Current state.
 * @param action - Transition to apply.
 * @returns The next state.
 */
export function conversationReducer(
  state: ConversationState,
  action: ConversationAction,
): ConversationState {
  switch (action.type) {
    case "started":
      return { ...state, threadId: action.threadId };
    case "open":
      return {
        epoch: state.epoch + 1,
        threadId: action.threadId,
        initialMessages: action.messages,
      };
    case "new":
      return {
        epoch: state.epoch + 1,
        threadId: null,
        initialMessages: [],
      };
  }
}

/**
 * Reads the thread query parameter.
 *
 * @param search - Location search string, with or without `?`.
 * @returns The thread id, or null when absent or empty.
 */
export function readThreadParam(search: string): string | null {
  const value = new URLSearchParams(search).get("thread");
  return value ? value : null;
}

/** One labeled group of threads in the rail. */
export interface ThreadGroup {
  label: string;
  items: ThreadSummary[];
}

/**
 * Groups threads by local calendar day, newest first.
 *
 * @param items - Thread summaries already sorted by update time.
 * @param now - Reference time, injected for tests.
 * @returns Non-empty groups with labels Today, Yesterday, or Earlier.
 */
export function groupThreads(items: ThreadSummary[], now: Date): ThreadGroup[] {
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const yesterday = new Date(
    now.getFullYear(),
    now.getMonth(),
    now.getDate() - 1,
  ).getTime();

  const groups: ThreadGroup[] = [
    { label: "Today", items: [] },
    { label: "Yesterday", items: [] },
    { label: "Earlier", items: [] },
  ];
  for (const item of items) {
    const updated = new Date(item.updated_at).getTime();
    if (!Number.isNaN(updated) && updated >= today) {
      groups[0].items.push(item);
    } else if (!Number.isNaN(updated) && updated >= yesterday) {
      groups[1].items.push(item);
    } else {
      groups[2].items.push(item);
    }
  }
  return groups.filter((group) => group.items.length > 0);
}
