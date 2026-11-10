import { expect, it } from "vitest";
import {
  conversationReducer,
  groupThreads,
  initialConversationState,
  readThreadParam,
} from "./conversation";

it("keeps the epoch when the first thread id arrives", () => {
  const state = conversationReducer(initialConversationState, {
    type: "started",
    threadId: "abc",
  });
  expect(state.threadId).toBe("abc");
  expect(state.epoch).toBe(initialConversationState.epoch);
});

it("bumps the epoch for new and opened threads", () => {
  const opened = conversationReducer(initialConversationState, {
    type: "open",
    threadId: "abc",
    messages: [],
  });
  expect(opened.epoch).toBe(initialConversationState.epoch + 1);
  expect(opened.threadId).toBe("abc");

  const fresh = conversationReducer(opened, { type: "new" });
  expect(fresh.epoch).toBe(opened.epoch + 1);
  expect(fresh.threadId).toBeNull();
});

it("reads the thread query parameter", () => {
  expect(readThreadParam("?thread=abc")).toBe("abc");
  expect(readThreadParam("")).toBeNull();
});

it("groups threads by local day", () => {
  const now = new Date(2026, 10, 10, 12);
  const at = (y: number, m: number, d: number, h: number) =>
    new Date(y, m, d, h).toISOString();
  const groups = groupThreads(
    [
      { thread_id: "a", title: "", created_at: "", updated_at: at(2026, 10, 9, 9) },
      { thread_id: "b", title: "", created_at: "", updated_at: at(2026, 10, 10, 9) },
      { thread_id: "c", title: "", created_at: "", updated_at: at(2026, 10, 1, 9) },
    ],
    now,
  );
  expect(groups.map((group) => group.label)).toEqual(["Today", "Yesterday", "Earlier"]);
});
