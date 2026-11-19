import { expect, it } from "vitest";
import { chatRequest } from "./chat-request";

it("omits thread_id for a new thread and includes it afterwards", () => {
  expect(chatRequest([], null).body).not.toHaveProperty("thread_id");
  expect(chatRequest([], "abc").body.thread_id).toBe("abc");
});

it("sends reasoning only when it is set", () => {
  expect(chatRequest([], null, null).body).not.toHaveProperty("reasoning");
  expect(chatRequest([], null, "high").body.reasoning).toBe("high");
});
